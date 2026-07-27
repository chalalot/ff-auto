"""One multimodal completion seam: system prompt + text + image in ONE request.

Both consumers of image-aware models go through here:

* :class:`backend.tools.vision_tool.VisionTool` — a CrewAI tool wrapper, because a
  CrewAI agent's own messages are text-only, so a crew can only reach pixels
  through a tool call.
* :class:`backend.workflows.image_to_prompt_workflow.ImageToPromptWorkflow` — calls
  this directly, so the model that writes the prompt is the model that sees the
  reference (no lossy text summary in between).

Provider differences (OpenAI/Grok base64 content blocks vs. Google's native
``contents=[text, PIL.Image]``) are resolved here and nowhere else.
"""

import base64
import logging
import mimetypes
import os
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import PIL.Image

from backend.config import GlobalConfig
from backend.services.pipeline_trace import record_llm_call

logger = logging.getLogger(__name__)


class VisionLLMError(RuntimeError):
    """Raised when the multimodal call cannot be made or the model returns nothing."""


# Bare/retired Google model names callers may still have stored in configs.
GEMINI_ALIASES = {
    "gemini-1.5-pro": "gemini-2.5-flash",
    "gemini-1.5-flash": "gemini-2.5-flash",
    "gemini-1.0-pro": "gemini-2.5-flash",
}

GOOGLE_PREFIXES = ("gemini", "gemma")

_MAGIC_MIME = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)


def resolve_model(model_name: str) -> Tuple[str, str]:
    """Return ``(provider, resolved_model_name)`` for a configured model name."""
    lowered = (model_name or "").lower()
    if lowered.startswith(GOOGLE_PREFIXES):
        resolved = GEMINI_ALIASES.get(model_name, model_name)
        if resolved != model_name:
            logger.warning(
                "[vision_llm] model '%s' is deprecated, using '%s' instead",
                model_name,
                resolved,
            )
        return "google", resolved
    if lowered.startswith("grok"):
        return "grok", model_name
    return "openai", model_name


def _sniff_mime(path: str, header: bytes) -> str:
    """Real mime type of the reference — never assume JPEG.

    Google rejects a mismatched ``mime_type``, and it is the one field a caller
    cannot supply from the file path alone.
    """
    for magic, mime in _MAGIC_MIME:
        if header.startswith(magic):
            return mime
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "image/jpeg"


def _clean_path(image_path: str) -> str:
    """Strip quotes an LLM may wrap around a path it echoed back."""
    return image_path.strip().strip("'").strip('"')


def _read_image(image_path: str) -> bytes:
    if not os.path.exists(image_path):
        raise VisionLLMError(f"Image file not found at {image_path}")
    try:
        with open(image_path, "rb") as image_file:
            return image_file.read()
    except OSError as exc:
        raise VisionLLMError(f"Cannot read image file {image_path}: {exc}") from exc


def complete(
    model_name: str,
    prompt: str,
    image_path: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Send ``system_prompt`` + ``prompt`` (+ the image, when given) as one request.

    ``max_tokens`` is only applied on the OpenAI-compatible route; the Google
    route is left at the provider default so a low cap cannot eat a thinking
    model's budget before it answers.

    Raises :class:`VisionLLMError` on a missing key/file or an empty response.
    """
    provider, resolved_model = resolve_model(model_name)
    if image_path:
        image_path = _clean_path(image_path)

    trace_request = {
        "provider": provider,
        "model": resolved_model,
        "system_prompt": system_prompt,
        "prompt": prompt,
        "max_tokens": max_tokens,
        # The image is described, never inlined — a base64 reference would blow
        # the trace payload limit and tell the reader nothing.
        "image": {"path": image_path} if image_path else None,
    }
    started_at = datetime.now(timezone.utc)

    # Reading the reference is inside the traced region: an unreadable file is a
    # failure of this call and must show up in the run trace like any other.
    try:
        image_bytes: Optional[bytes] = None
        mime_type: Optional[str] = None
        if image_path:
            image_bytes = _read_image(image_path)
            mime_type = _sniff_mime(image_path, image_bytes[:16])
            trace_request["image"] = {
                "path": image_path,
                "mime_type": mime_type,
                "bytes": len(image_bytes),
            }

        if provider == "google":
            text, usage = _complete_google(
                resolved_model, model_name, prompt, image_path, system_prompt
            )
        else:
            text, usage = _complete_openai_compatible(
                provider, resolved_model, prompt, image_bytes, mime_type,
                system_prompt, max_tokens,
            )
    except VisionLLMError as exc:
        _trace(trace_request, None, resolved_model, started_at, error=exc)
        raise
    except Exception as exc:
        _trace(trace_request, None, resolved_model, started_at, error=exc)
        raise VisionLLMError(f"{provider} vision call failed: {exc}") from exc

    if not text or not text.strip():
        error = VisionLLMError(
            f"{provider} model {resolved_model} returned an empty response"
        )
        _trace(trace_request, None, resolved_model, started_at, error=error)
        raise error

    _trace(trace_request, {"text": text, "usage": usage}, resolved_model, started_at)
    return text


def _trace(
    request: dict,
    response: Optional[dict],
    model: str,
    started_at: datetime,
    error: Optional[BaseException] = None,
) -> None:
    """Record the call on the active pipeline step, if any."""
    payload = {
        "request": request,
        "response": response,
        "model": model,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is not None:
        payload["error"] = {"type": type(error).__name__, "message": str(error)}
    record_llm_call(payload)


def _complete_google(
    resolved_model: str,
    requested_model: str,
    prompt: str,
    image_path: Optional[str],
    system_prompt: Optional[str],
) -> Tuple[str, Optional[dict]]:
    api_key = GlobalConfig.GEMINI_API_KEY
    if not api_key:
        raise VisionLLMError("GEMINI_API_KEY not found in environment variables.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise VisionLLMError("google-genai library not installed.") from exc

    client = genai.Client(api_key=api_key)
    logger.info("[vision_llm] Google GenAI request, model=%s", resolved_model)

    # Gemma's native Gemini-API surface takes no separate system role, so the
    # contract is folded into the user content on that route only.
    effective_prompt = prompt
    config = None
    if requested_model.lower().startswith("gemma"):
        if system_prompt:
            effective_prompt = f"{system_prompt}\n\n{prompt}"
    else:
        config = types.GenerateContentConfig(system_instruction=system_prompt or None)

    contents: list = [effective_prompt]
    if image_path:
        contents.append(PIL.Image.open(image_path))

    response = client.models.generate_content(
        model=resolved_model,
        contents=contents,
        config=config,
    )
    return response.text, _usage_of(getattr(response, "usage_metadata", None))


def _complete_openai_compatible(
    provider: str,
    resolved_model: str,
    prompt: str,
    image_bytes: Optional[bytes],
    mime_type: Optional[str],
    system_prompt: Optional[str],
    max_tokens: Optional[int],
) -> Tuple[str, Optional[dict]]:
    from openai import OpenAI

    if provider == "grok":
        api_key = GlobalConfig.GROK_API_KEY
        if not api_key:
            raise VisionLLMError("GROK_API_KEY not found in environment variables.")
        client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    else:
        client = OpenAI()  # picks up OPENAI_API_KEY / OPENAI_BASE_URL from env

    logger.info("[vision_llm] %s request, model=%s", provider, resolved_model)

    messages: list = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if image_bytes is None:
        messages.append({"role": "user", "content": prompt})
    else:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                },
            ],
        })

    kwargs: dict = {"model": resolved_model, "messages": messages}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content, _usage_of(
        getattr(response, "usage", None)
    )


def _usage_of(usage: Any) -> Optional[dict]:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:  # pragma: no cover - defensive, usage is never critical
            return None
    if isinstance(usage, dict):
        return usage
    return None
