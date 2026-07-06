import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Union

from backend.config import GlobalConfig


class LLMEvaluatorClient:
    """OpenAI-compatible client for production-quality media evaluation."""

    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
    ):
        configured_model = model or GlobalConfig.EVALUATOR_MODEL
        self.api_key = api_key or GlobalConfig.EVALUATOR_API_KEY
        self.base_url = base_url or GlobalConfig.EVALUATOR_API_BASE
        self.model = self._normalize_model(configured_model)

    def _normalize_model(self, model: str) -> str:
        if self.base_url and "googleapis.com" in self.base_url:
            if model.startswith("google/"):
                return model.removeprefix("google/")
            if model.startswith("models/"):
                return model.removeprefix("models/")
        return model

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("EVALUATOR_API_KEY or OPENAI_API_KEY is required.")

        from openai import OpenAI

        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self._system_prompt(payload["rubric"]),
                },
                {"role": "user", "content": self._user_content(payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        return content or ""

    def _system_prompt(self, rubric: Dict[str, Dict[str, Any]]) -> str:
        rubric_text = self._format_rubric(rubric)
        dimensions = ", ".join(rubric.keys())
        return (
            "You are a strict production-quality evaluator for generated media. "
            "Inspect the attached media pixels directly; do not infer quality from "
            "the filename, path, or generation prompt alone. "
            "Evaluate only production quality. Do not evaluate social media appeal, "
            "first-three-second hook, platform readiness, or scene transition strategy. "
            f"Return JSON only with scores for exactly these dimensions: {dimensions}. "
            "Each score must be an integer from 1 to 5 and include textual rationale. "
            "Return shape: {\"scores\":[{\"dimension\":\"...\",\"score\":1,"
            "\"rationale\":\"...\"}],\"summary\":\"...\"}.\n\n"
            f"Production rubric:\n{rubric_text}"
        )

    def _format_rubric(self, rubric: Dict[str, Dict[str, Any]]) -> str:
        sections = []
        for dimension, guideline in rubric.items():
            anchors = guideline["score_anchors"]
            exclusions = ", ".join(guideline["do_not_score"])
            sections.append(
                "\n".join(
                    [
                        f"- {dimension}",
                        f"  Definition: {guideline['definition']}",
                        f"  Score 1: {anchors[1]}",
                        f"  Score 3: {anchors[3]}",
                        f"  Score 5: {anchors[5]}",
                        f"  Do not score: {exclusions}.",
                    ]
                )
            )
        return "\n".join(sections)

    def _user_content(self, payload: Dict[str, Any]) -> Union[str, List[Dict[str, Any]]]:
        prompt = self._user_prompt(payload)
        if payload["media_type"] != "image":
            return prompt

        image_url = self._image_url(payload["media_path"])
        return [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]

    def _image_url(self, media_path: str) -> str:
        if media_path.startswith(("http://", "https://", "data:")):
            return media_path

        media_root = Path(GlobalConfig.EVALUATION_MEDIA_ROOT).resolve()
        path = (media_root / media_path).resolve()
        try:
            path.relative_to(media_root)
        except ValueError:
            raise ValueError(
                f"Media path escapes the allowed media root: {media_path}"
            )
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file is not readable: {media_path}")

        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        if not mime_type.startswith("image/"):
            raise ValueError(f"Media path is not an image file: {media_path}")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _user_prompt(self, payload: Dict[str, Any]) -> str:
        prompt = payload.get("prompt") or ""
        return (
            f"Media type: {payload['media_type']}\n"
            f"Media path or URL: {payload['media_path']}\n"
            f"Original generation prompt/context: {prompt}\n"
            "Score the generated media against the production rubric. For images, "
            "base the scores on the attached image pixels. Penalize obvious extra "
            "objects, duplicated objects, mismatched limbs/clothing/footwear, warped "
            "anatomy, impossible object placement, or prompt-image mismatches."
        )
