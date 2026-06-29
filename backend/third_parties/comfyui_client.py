"""
ComfyUI API Client for Image Generation

Provides async image generation capabilities using ComfyUI API including:
- Image generation with custom prompts
- Status checking and polling
- Image download and S3 upload
- Robust error handling and retry logic
- Marketing-focused prompt templates

Features:
- Async support for non-blocking operations
- Configurable timeout and polling parameters
- Error handling with exponential backoff
- S3 integration for image storage
- Marketing campaign optimization
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "httpx package is required. Install with: pip install httpx"
    ) from exc

from backend.config import GlobalConfig
from backend.utils.image_filters import apply_stable_film_look
from backend.utils.constants import DEFAULT_NEGATIVE_PROMPT
from .comfyui_queue_manager import execute_with_queue

# Set up logging
logger = logging.getLogger(__name__)

# Rate limiting configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 2.0  # Base delay in seconds
DEFAULT_MAX_DELAY = 60.0  # Maximum delay in seconds
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_JITTER_RANGE = 0.1  # ±10% jitter to prevent thundering herd
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
DEFAULT_RESPONSE_PREVIEW_CHARS = 500
COMFYUI_SUCCESS_STATUSES = {"success", "completed"}
COMFYUI_FAILED_STATUSES = {
    "failed",
    "failure",
    "error",
    "lost",
    "canceled",
    "cancelled",
    "timeout",
    "timed_out",
}

# ComfyUI configuration from GlobalConfig
CLOUD_COMFY_API_URL = GlobalConfig.CLOUD_COMFY_API_URL
COMFYUI_API_KEY = GlobalConfig.COMFYUI_API_KEY
COMFYUI_API_TIMEOUT = GlobalConfig.COMFYUI_API_TIMEOUT
COMFYUI_POLL_INTERVAL = GlobalConfig.COMFYUI_POLL_INTERVAL
COMFYUI_MAX_POLL_TIME = GlobalConfig.COMFYUI_MAX_POLL_TIME
COMFYUI_MAX_RETRIES = GlobalConfig.COMFYUI_MAX_RETRIES

# Persona mappings
PERSONA_LORA_MAPPING_TURBO = {
    "Jennie": "khiemle__xz-comfy__jennie_turbo_v4.safetensors",
    "Sephera": "khiemle__xz-comfy__sephera_turbo_v6.safetensors",
    "Nya": "khiemle__xz-comfy__nya_turbo_v1.safetensors",
    "Emi": "khiemle__xz-comfy__emi_turbo_v2.safetensors",
    "Roxie": "khiemle__xz-comfy__roxie_v3.safetensors"
}


def _calculate_backoff_delay(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
    jitter_range: float = DEFAULT_JITTER_RANGE
) -> float:
    """Calculate exponential backoff delay with jitter."""
    delay = base_delay * (multiplier ** attempt)
    delay = min(delay, max_delay)

    # Add jitter to prevent thundering herd
    jitter = delay * jitter_range * (2 * random.random() - 1)
    delay += jitter

    return max(0, delay)


def _response_text_preview(text: str, max_chars: int = DEFAULT_RESPONSE_PREVIEW_CHARS) -> str:
    """Keep proxy HTML/error pages readable in logs and exceptions."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}..."


def _workflow_node_inputs(node: Any) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return {}
    return inputs


def _workflow_nodes(
    workflow_data: Dict[str, Any],
    class_type: str,
    required_inputs: Optional[set[str]] = None,
) -> list[Dict[str, Any]]:
    required_inputs = required_inputs or set()
    matches = []

    for node in workflow_data.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != class_type:
            continue
        inputs = _workflow_node_inputs(node)
        if required_inputs.issubset(inputs.keys()):
            matches.append(node)

    return matches


def _find_workflow_node(
    workflow_data: Dict[str, Any],
    class_type: str,
    required_inputs: Optional[set[str]] = None,
    legacy_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    required_inputs = required_inputs or set()

    for node in workflow_data.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != class_type:
            continue
        inputs = _workflow_node_inputs(node)
        if required_inputs.issubset(inputs.keys()):
            return node

    if legacy_id:
        legacy_node = workflow_data.get(legacy_id)
        if isinstance(legacy_node, dict):
            inputs = _workflow_node_inputs(legacy_node)
            if required_inputs.issubset(inputs.keys()):
                return legacy_node

    return None


def _find_lora_workflow_node(workflow_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lora_classes = {"LoraLoaderModelOnly", "LoraLoader"}
    required_inputs = {"lora_name", "strength_model"}

    for node in workflow_data.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") not in lora_classes:
            continue
        inputs = _workflow_node_inputs(node)
        if required_inputs.issubset(inputs.keys()):
            return node

    legacy_node = workflow_data.get("53")
    if isinstance(legacy_node, dict):
        inputs = _workflow_node_inputs(legacy_node)
        if required_inputs.issubset(inputs.keys()):
            return legacy_node

    return None


def _patch_workflow_dimensions(workflow_data: Dict[str, Any], width: str, height: str) -> None:
    final_width = int(width)
    final_height = int(height)

    upscale_nodes = _workflow_nodes(
        workflow_data,
        class_type="ImageScale",
        required_inputs={"width", "height"},
    )

    latent_node = _find_workflow_node(
        workflow_data,
        class_type="EmptySD3LatentImage",
        required_inputs={"width", "height"},
        legacy_id="41",
    )

    if upscale_nodes:
        # We have an upscale workflow. Set target to upscale node, and base latent to half.
        for upscale_node in upscale_nodes:
            upscale_inputs = _workflow_node_inputs(upscale_node)
            upscale_inputs["width"] = final_width
            upscale_inputs["height"] = final_height

        if latent_node:
            latent_inputs = _workflow_node_inputs(latent_node)
            latent_inputs["width"] = final_width // 2
            latent_inputs["height"] = final_height // 2
    else:
        # Standard workflow without upscaling
        if latent_node:
            latent_inputs = _workflow_node_inputs(latent_node)
            latent_inputs["width"] = final_width
            latent_inputs["height"] = final_height
        else:
            logger.warning("No EmptySD3LatentImage width/height node found while patching workflow.")


def _patch_sampler_seeds(
    workflow_data: Dict[str, Any],
    seed_strategy: str,
    base_seed: int,
) -> None:
    sampler_nodes = _workflow_nodes(
        workflow_data,
        class_type="KSampler",
        required_inputs={"seed"},
    )
    if not sampler_nodes:
        legacy_node = workflow_data.get("44")
        if isinstance(legacy_node, dict) and "seed" in _workflow_node_inputs(legacy_node):
            sampler_nodes = [legacy_node]

    if not sampler_nodes:
        logger.warning("No KSampler seed node found while patching workflow.")
        return

    for index, sampler_node in enumerate(sampler_nodes):
        sampler_inputs = _workflow_node_inputs(sampler_node)
        if seed_strategy == "random":
            sampler_inputs["seed"] = random.randint(1, 1000000000000000)
        else:
            sampler_inputs["seed"] = int(base_seed) + index


def _extract_comfy_error_message(status_payload: Dict[str, Any]) -> str:
    raw_error = (
        status_payload.get("error_message")
        or status_payload.get("error")
        or status_payload.get("exception_message")
        or status_payload
    )

    if isinstance(raw_error, str):
        try:
            raw_error = json.loads(raw_error)
        except json.JSONDecodeError:
            return raw_error

    if isinstance(raw_error, dict):
        exception_message = (
            raw_error.get("exception_message")
            or raw_error.get("message")
            or raw_error.get("error_message")
            or raw_error.get("error")
        )
        node_id = raw_error.get("node_id")
        node_type = raw_error.get("node_type")
        parts = []
        if exception_message:
            parts.append(str(exception_message).strip())
        if node_id or node_type:
            node_label = f"node {node_id}" if node_id else "node"
            if node_type:
                node_label = f"{node_label} ({node_type})"
            parts.append(node_label)
        if parts:
            return " at ".join(parts)

    return json.dumps(raw_error, ensure_ascii=False)


class ComfyUIError(Exception):
    """Base exception for ComfyUI API errors."""
    pass


class ComfyUITimeoutError(ComfyUIError):
    """Raised when image generation times out."""
    pass


class ComfyUIAPIError(ComfyUIError):
    """Raised when ComfyUI API returns an error."""
    pass


class ComfyUIConfigError(ComfyUIError):
    """Raised when ComfyUI configuration is invalid (e.g., bad URL)."""
    pass

class ComfyUIClient:
    """
    Async client for ComfyUI image generation API via Comfy Cloud.

    Handles the complete workflow:
    1. Submit generation request using local workflow.json
    2. Poll for completion status
    3. Download generated image
    4. Upload to GCS
    """

    def __init__(
        self,
        cloud_api_url: str = CLOUD_COMFY_API_URL,
        api_key: Optional[str] = COMFYUI_API_KEY,
        timeout: int = COMFYUI_API_TIMEOUT,
        poll_interval: int = COMFYUI_POLL_INTERVAL,
        max_poll_time: int = COMFYUI_MAX_POLL_TIME,
        max_retries: int = COMFYUI_MAX_RETRIES
    ):
        if not cloud_api_url or not str(cloud_api_url).strip():
            raise ComfyUIConfigError(
                "CLOUD_COMFY_API_URL is not set."
            )

        self.cloud_api_url = cloud_api_url.rstrip('/')
        self.api_key = api_key.strip() if api_key else None
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self.max_retries = max_retries

    async def get_queue(self) -> Dict[str, Any]:
        """
        Fetch the current queue status from ComfyUI API.
        Returns the queue running and pending lists.
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        url = f"{self.cloud_api_url}/queue"

        logger.info(f"🔵 ComfyUI Cloud Request: GET {url}")
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Get queue HTTP Error ({e.response.status_code}): {e.response.text}")
            raise ComfyUIAPIError(f"Get queue failed ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Failed to get queue: {e}")
            raise ComfyUIAPIError(f"Get queue failed: {e}")

    async def queue_prompt(self, prompt_workflow: Dict[str, Any]) -> str:
        """
        Queue a prompt to the Cloud ComfyUI API (Standard /prompt endpoint).
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        url = f"{self.cloud_api_url}/prompt"

        # Comfy Cloud format
        payload = {
            "prompt": prompt_workflow
        }

        logger.info(f"🔵 ComfyUI Cloud Request: POST {url}")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            # Comfy Cloud uses X-API-Key or Authorization
            headers["X-API-Key"] = self.api_key
            # Inject extra_data for Partner Nodes (like Kling) to authenticate
            payload["extra_data"] = {
                "api_key_comfy_org": self.api_key
            }

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    prompt_id = data.get("prompt_id")
                    if not prompt_id:
                        raise ComfyUIAPIError(f"Queue prompt response missing prompt_id: {data}")
                    logger.info(f"✅ Prompt queued: {data}")
                    return prompt_id
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                response_preview = _response_text_preview(e.response.text)
                should_retry = (
                    status_code in TRANSIENT_HTTP_STATUS_CODES
                    and attempt < self.max_retries
                )
                if should_retry:
                    delay = _calculate_backoff_delay(attempt)
                    logger.warning(
                        "⚠️ Queue prompt transient HTTP Error (%s), retrying in %.1fs "
                        "(attempt %s/%s): %s",
                        status_code,
                        delay,
                        attempt + 1,
                        self.max_retries + 1,
                        response_preview,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"❌ Queue prompt HTTP Error ({status_code}): {response_preview}")
                raise ComfyUIAPIError(f"Queue prompt failed ({status_code}): {response_preview}") from e
            except ComfyUIAPIError:
                raise
            except Exception as e:
                logger.error(f"❌ Failed to queue prompt: {e}")
                raise ComfyUIAPIError(f"Queue prompt failed: {e}") from e

        raise ComfyUIAPIError("Queue prompt failed after retry exhaustion")

    async def generate_image(
        self,
        positive_prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        workflow_type: str = "turbo",
        lora_name: Optional[str] = None,
        kol_persona: Optional[str] = None,
        strength_model: Optional[str] = None,
        seed_strategy: str = "random",
        base_seed: int = 0,
        width: str = "1024",
        height: str = "1600",
        clip_model_type: str = "qwen_image",
        pipeline_type: str = "image.subject_environment",
        workflow_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        workflow_name: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Start image generation via Comfy Cloud API using workflow.json.

        Workflow construction is delegated to the selected generation pipeline
        (see ``backend.pipelines``); this client only submits the result. The
        default ``image.subject_environment`` pipeline auto-detects
        ``#Subject`` / ``#Environment`` prompts and falls back to a single CLIP
        node, preserving the original generate_image behaviour.
        """
        # Imported lazily: the pipelines package imports node-patching helpers
        # from this module at load time, so a top-level import would cycle.
        from backend.pipelines import GenerationInputs, get_pipeline

        logger.info("=" * 80)
        logger.info("🎨 COMFYUI IMAGE GENERATION REQUEST (CLOUD API)")
        logger.info(f"🧩 Pipeline: {pipeline_type}")
        logger.info(
            f"📝 Prompt: {positive_prompt[:200]}{'...' if len(positive_prompt) > 200 else ''}"
        )
        logger.info("=" * 80)

        inputs = GenerationInputs(
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            lora_name=lora_name,
            kol_persona=kol_persona,
            strength_model=strength_model,
            seed_strategy=seed_strategy,
            base_seed=base_seed,
            width=width,
            height=height,
            clip_model_type=clip_model_type,
            workflow_overrides=workflow_overrides or {},
            workflow_name=workflow_name,
        )

        pipeline = get_pipeline(pipeline_type)
        return await pipeline.run(inputs, client=self)

    async def check_status(self, execution_id: str) -> Dict[str, Any]:
        """
        Check the status of image generation.
        """
        async def _status_request():
            if not self.cloud_api_url:
                raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

            # Cloud API first uses /job/{prompt_id}/status to check if complete
            status_url = f"{self.cloud_api_url}/job/{execution_id}/status"
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    # 1. Check job status
                    status_response = await client.get(status_url, headers=headers)
                    status_response.raise_for_status()
                    status_payload = status_response.json()
                    job_status = status_payload.get("status", "").lower()

                    if job_status in COMFYUI_SUCCESS_STATUSES:
                        # 2. If completed, get history to find output filename
                        history_url = f"{self.cloud_api_url}/history_v2/{execution_id}"
                        history_response = await client.get(history_url, headers=headers)
                        history_response.raise_for_status()
                        history_data = history_response.json()

                        job_data = history_data.get(execution_id, {})
                        outputs = job_data.get("outputs", {})
                        output_images = []

                        # Flatten outputs
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                paths = []
                                for img in node_output["images"]:
                                    fname = img.get("filename")
                                    sub = img.get("subfolder", "")
                                    ftype = img.get("type", "output")
                                    # Construct path that we can download later
                                    paths.append(f"{sub}/{fname}?type={ftype}" if sub else f"{fname}?type={ftype}")

                                output_images.append({node_id: paths})

                        return {
                            "status": "completed",
                            "output_images": output_images,
                            "raw_history": history_data
                        }

                    elif job_status in COMFYUI_FAILED_STATUSES:
                        return {
                            "status": "failed",
                            "error_message": _extract_comfy_error_message(status_payload),
                            "raw_status": status_payload,
                        }

                    else:
                        # pending, running, etc.
                        return {"status": "running"}

                except httpx.HTTPStatusError as e:
                    logger.error(f"Status check failed ({e.response.status_code}): {e.response.text}")
                    # In some APIs, if job hasn't started yet, it might 404. We'll assume running if 404 for now.
                    if e.response.status_code == 404:
                        return {"status": "running"}
                    raise

        try:
            # Queue status requests to prevent concurrent polling
            return await execute_with_queue(
                operation=_status_request,
                description=f"Status check for {execution_id}",
                timeout=30  # Shorter timeout for status checks
            )

        except Exception as e:
            logger.error(f"Failed to check status for {execution_id}: {e}")
            raise

    async def wait_for_completion(
        self,
        execution_id: str,
        poll_interval: Optional[int] = None,
        max_poll_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Poll for completion of image generation.

        Args:
            execution_id: ID from generate_image()
            poll_interval: Seconds between status checks
            max_poll_time: Maximum time to wait in seconds
            is_cloud: Whether to check status on Cloud API

        Returns:
            Final status data when completed
        """
        poll_interval = poll_interval or self.poll_interval
        max_poll_time = max_poll_time or self.max_poll_time

        start_time = time.time()

        while True:
            elapsed = time.time() - start_time

            if elapsed > max_poll_time:
                raise ComfyUITimeoutError(f"Generation timed out after {max_poll_time}s")

            try:
                status_data = await self.check_status(execution_id)
                status = status_data.get("status")

                logger.info(f"⏳ Status check [{elapsed:.0f}s elapsed]: {status}")

                if status == "completed":
                    logger.info("=" * 80)
                    logger.info(f"✅ IMAGE GENERATION COMPLETED")
                    logger.info("=" * 80)
                    logger.info(f"🔑 Execution ID: {execution_id}")
                    logger.info(f"⏱️  Total time elapsed: {elapsed:.1f}s")
                    logger.info(f"📊 Status Data: {json.dumps(status_data, indent=2)}")
                    logger.info("=" * 80)
                    return status_data
                elif status == "failed":
                    error_msg = status_data.get("error_message", "Unknown error")
                    raise ComfyUIAPIError(f"Generation failed: {error_msg}")
                elif status in ["queued", "running"]:
                    # Still in progress
                    logger.info(f"   Waiting... (status: {status}, {elapsed:.0f}s/{max_poll_time}s)")
                    await asyncio.sleep(poll_interval)
                    continue
                else:
                    logger.warning(f"Unknown status '{status}' for {execution_id}")
                    await asyncio.sleep(poll_interval)

            except ComfyUIError:
                raise
            except Exception as e:
                logger.error(f"Error while polling status: {e}")
                await asyncio.sleep(poll_interval)

    async def upload_image(self, image_path: str) -> str:
        """
        Upload a local image to ComfyUI Cloud so it can be referenced in a workflow.

        Returns:
            The filename as stored on the ComfyUI server (use this in LoadImage nodes).
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        url = f"{self.cloud_api_url}/upload/image"
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        image_name = os.path.basename(image_path)
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine content type from extension
        ext = os.path.splitext(image_name)[1].lower()
        content_type = "image/png" if ext == ".png" else "image/jpeg"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=headers,
                files={"image": (image_name, image_data, content_type)},
            )
            response.raise_for_status()
            data = response.json()
            # ComfyUI returns {"name": "...", "subfolder": "...", "type": "input"}
            return data.get("name", image_name)

    async def generate_video_comfy(
        self,
        image_path: str,
        prompt: str = "",
        negative_prompt: str = "",
        model_name: str = "kling-v2-5-turbo",
        cfg_scale: float = 0.5,
        mode: str = "std",
        aspect_ratio: str = "9:16",
        duration: str = "5",
        kling_workflow_path: Optional[str] = None,
    ) -> str:
        """
        Submit a Kling image-to-video job via the ComfyUI KlingImage2VideoNode workflow.

        Loads kling.json, injects the parameters, uploads the source image,
        and submits via queue_prompt().

        Returns:
            prompt_id (execution ID) from ComfyUI.
        """
        # Resolve workflow path
        if kling_workflow_path is None:
            kling_workflow_path = os.getenv(
                "KLING_WORKFLOW_JSON_PATH",
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "kling.json",
                ),
            )

        with open(kling_workflow_path, "r") as f:
            workflow = json.load(f)

        # Upload the source image to ComfyUI first so it can be referenced by filename
        logger.info(f"[generate_video_comfy] Uploading image to ComfyUI Cloud: {image_path}")
        uploaded_filename = await self.upload_image(image_path)
        logger.info(f"[generate_video_comfy] Image uploaded as: {uploaded_filename}")

        # Patch LoadImage node (node 40) with the uploaded filename
        if "40" in workflow:
            workflow["40"]["inputs"]["image"] = uploaded_filename

        # Patch KlingImage2VideoNode (node 45) with user params
        if "45" in workflow:
            node = workflow["45"]["inputs"]
            node["prompt"] = prompt
            node["negative_prompt"] = negative_prompt
            node["model_name"] = model_name
            node["cfg_scale"] = cfg_scale
            node["mode"] = mode
            node["aspect_ratio"] = aspect_ratio
            node["duration"] = duration

        prompt_id = await self.queue_prompt(workflow)
        logger.info(f"[generate_video_comfy] Queued Kling ComfyUI job: {prompt_id}")
        return prompt_id

    async def check_video_status(self, execution_id: str) -> Dict[str, Any]:
        """
        Check status of a ComfyUI video job. Handles both 'images' and 'videos'/'gifs'
        output types from SaveVideo / VHS_VideoCombine nodes.

        Returns the same shape as check_status() but with 'output_videos' instead of
        'output_images' when video outputs are found.
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        status_url = f"{self.cloud_api_url}/job/{execution_id}/status"
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            status_response = await client.get(status_url, headers=headers)
            status_response.raise_for_status()
            status_payload = status_response.json()
            job_status = status_payload.get("status", "").lower()

            if job_status in COMFYUI_SUCCESS_STATUSES:
                history_url = f"{self.cloud_api_url}/history_v2/{execution_id}"
                history_response = await client.get(history_url, headers=headers)
                history_response.raise_for_status()
                history_data = history_response.json()

                job_data = history_data.get(execution_id, {})
                outputs = job_data.get("outputs", {})

                output_videos: list = []
                output_images: list = []

                for node_id, node_output in outputs.items():
                    # Handle video outputs (SaveVideo / VHS_VideoCombine)
                    for video_key in ("videos", "gifs", "video"):
                        if video_key in node_output:
                            paths = []
                            for item in node_output[video_key]:
                                fname = item.get("filename", "")
                                sub = item.get("subfolder", "")
                                ftype = item.get("type", "output")
                                paths.append(f"{sub}/{fname}?type={ftype}" if sub else f"{fname}?type={ftype}")
                            output_videos.append({node_id: paths})

                    # Handle image outputs (fallback)
                    if "images" in node_output:
                        paths = []
                        for img in node_output["images"]:
                            fname = img.get("filename", "")
                            sub = img.get("subfolder", "")
                            ftype = img.get("type", "output")
                            paths.append(f"{sub}/{fname}?type={ftype}" if sub else f"{fname}?type={ftype}")
                        output_images.append({node_id: paths})

                return {
                    "status": "completed",
                    "output_videos": output_videos,
                    "output_images": output_images,
                    "raw_history": history_data,
                }

            elif job_status in COMFYUI_FAILED_STATUSES:
                return {
                    "status": "failed",
                    "error_message": _extract_comfy_error_message(status_payload),
                    "raw_status": status_payload,
                }
            else:
                return {"status": "running"}

    async def download_file_by_path(self, file_path: str) -> bytes:
        """
        Download any file (image or video) from ComfyUI /view endpoint by path string.
        Same logic as download_image_by_path but generalized.
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        filename_part = file_path.split("?")[0]
        query_part = file_path.split("?")[1] if "?" in file_path else "type=output"

        view_url = f"{self.cloud_api_url}/view?filename={os.path.basename(filename_part)}&{query_part}"
        if "/" in filename_part:
            sub = os.path.dirname(filename_part)
            view_url += f"&subfolder={sub}"

        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(view_url, headers=headers)
            resp.raise_for_status()
            return resp.content

    async def generate_and_wait(
        self,
        positive_prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        product_name: Optional[str] = None,
        kol_persona: Optional[str] = None,
        image_type: str = "marketing",
        upload_to_gcs: Optional[bool] = None,
        run_id: Optional[str] = None,
        lora_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Complete image generation workflow: generate, wait, download, and optionally upload to GCS.
        """
        if upload_to_gcs is None:
            upload_to_gcs = getattr(GlobalConfig, "UPLOAD_GCS", True)

        async def _execute_generation():
            execution_id = await self.generate_image(
                positive_prompt,
                negative_prompt,
                lora_name=lora_name,
                kol_persona=kol_persona,
                **kwargs
            )
            status_data = await self.wait_for_completion(execution_id)
            return execution_id, status_data

        # Use queue manager to ensure sequential processing
        description = f"Image generation for {kol_persona or 'unknown'} - {product_name or 'unknown'}"

        # Try to get current Celery task ID if available
        celery_task_id = None
        try:
            from celery import current_task
            if current_task and current_task.request.id:
                celery_task_id = current_task.request.id
        except ImportError:
            pass
        except AttributeError:
            pass
        except Exception:
            pass

        execution_id, status_data = await execute_with_queue(
            operation=_execute_generation,
            description=description,
            timeout=self.max_poll_time + 120,  # Add buffer time for queue waiting
            celery_task_id=celery_task_id
        )

        try:
            # Extract image path from output_images
            output_images = status_data.get("output_images", [])

            if not output_images:
                logger.error(f"❌ No output_images in status response for {execution_id}")
                raise ComfyUIAPIError(f"No output images available for execution {execution_id}")

            # Get first image path
            first_output = output_images[0]
            image_path = None
            for key, paths in first_output.items():
                if paths and len(paths) > 0:
                    image_path = paths[0]
                    break

            if not image_path:
                raise ComfyUIAPIError(f"No image path found in output_images for {execution_id}")

            logger.info(f"📁 Found image path: {image_path}")

            logger.info(f"📥 Attempting to download image for {execution_id}...")

            # Cloud API download via /view endpoint
            if not self.cloud_api_url:
                 raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

            filename_part = image_path.split('?')[0]
            query_part = image_path.split('?')[1] if '?' in image_path else "type=output"

            view_url = f"{self.cloud_api_url}/view?filename={os.path.basename(filename_part)}&{query_part}"
            if '/' in filename_part:
                sub = os.path.dirname(filename_part)
                view_url += f"&subfolder={sub}"

            logger.info(f"📥 Downloading from Cloud: {view_url}")
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(view_url, headers=headers)
                resp.raise_for_status()
                image_data = resp.content

            remote_url = view_url

            logger.info(f"✅ Downloaded {len(image_data)} bytes")

            # Apply stable film look filter
            image_data = apply_stable_film_look(image_data)

            result = {
                "execution_id": execution_id,
                "remote_url": remote_url,
                "image_bytes": image_data,
                "timestamp": datetime.now().isoformat(),
                "image_type": image_type,
                "upload_to_gcs": upload_to_gcs
            }

            # Upload to GCS if requested and metadata provided
            if upload_to_gcs and product_name and kol_persona:
                try:
                    from .gcs_client import upload_campaign_image, get_next_sequence_number

                    # Get next sequence number for this image type
                    if not run_id:
                        from .gcs_client import generate_run_id
                        run_id = generate_run_id(product_name, kol_persona)

                    sequence = get_next_sequence_number(run_id, image_type)

                    # Upload to GCS with structured organization
                    public_url, gcs_path, final_run_id = upload_campaign_image(
                        image_bytes=image_data,
                        product_name=product_name,
                        kol_persona=kol_persona,
                        image_type=image_type,
                        sequence=sequence,
                        run_id=run_id,
                        content_type="image/png"
                    )

                    # Add GCS info to result
                    result.update({
                        "gcs_uploaded": True,
                        "public_url": public_url,
                        "gcs_path": gcs_path,
                        "run_id": final_run_id,
                        "product_name": product_name,
                        "kol_persona": kol_persona,
                        "sequence": sequence
                    })

                    logger.info(f"Image uploaded to GCS: {gcs_path}")

                except Exception as gcs_error:
                    logger.error(f"GCS upload failed: {gcs_error}")
                    result.update({
                        "gcs_uploaded": False,
                        "gcs_error": str(gcs_error),
                        "public_url": remote_url,  # Fallback to ComfyUI URL
                        "product_name": product_name,
                        "kol_persona": kol_persona
                    })

            elif upload_to_gcs and (not product_name or not kol_persona):
                # Raise exception with detailed traceback instead of silent logging
                import traceback
                stack_info = ''.join(traceback.format_stack())
                error_msg = f"GCS upload requested but missing required campaign metadata:\n"
                error_msg += f"  - product_name: {'✓' if product_name else '✗ MISSING'} ({product_name})\n"
                error_msg += f"  - kol_persona: {'✓' if kol_persona else '✗ MISSING'} ({kol_persona})\n"
                error_msg += f"  - upload_to_gcs: {upload_to_gcs}\n\n"
                error_msg += f"Call stack:\n{stack_info}"

                logger.error(error_msg)
                raise ValueError(f"Missing required campaign metadata for GCS upload: product_name={product_name}, kol_persona={kol_persona}")
            else:
                # No GCS upload requested
                result.update({
                    "gcs_uploaded": False,
                    "public_url": remote_url
                })

            logger.info(f"Image generation workflow completed for {execution_id}")
            return result

        except Exception as e:
            logger.error(f"Image generation workflow failed: {e}")
            raise

    async def download_image_by_path(self, image_path: str) -> bytes:
        """
        Download an image directly by its path (filename and query parameters).
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")

        filename_part = image_path.split('?')[0]
        query_part = image_path.split('?')[1] if '?' in image_path else "type=output"

        view_url = f"{self.cloud_api_url}/view?filename={os.path.basename(filename_part)}&{query_part}"
        if '/' in filename_part:
            sub = os.path.dirname(filename_part)
            view_url += f"&subfolder={sub}"

        logger.info(f"📥 Downloading image via path from Cloud: {view_url}")
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(view_url, headers=headers)
            resp.raise_for_status()
            return resp.content

    async def download_image(self, execution_id: str) -> bytes:
        """
        Download an image by execution ID (fallback). Check status to get the path.
        """
        status_data = await self.check_status(execution_id)
        if status_data.get("status") != "completed":
            raise ComfyUIAPIError(f"Cannot download image for incomplete execution {execution_id}")

        output_images = status_data.get("output_images", [])
        if not output_images:
            raise ComfyUIAPIError(f"No output images found for execution {execution_id}")

        first_output = output_images[0]
        image_path = None
        for key, paths in first_output.items():
            if paths and len(paths) > 0:
                image_path = paths[0]
                break

        if not image_path:
            raise ComfyUIAPIError(f"No image path found in output_images for {execution_id}")

        return await self.download_image_by_path(image_path)

    async def generate_and_upload(
        self,
        positive_prompt: str,
        negative_prompt: str,
        product_name: str,
        kol_persona: str,
        image_type: str = "marketing",
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convenience method for generate + GCS upload workflow.

        Args:
            positive_prompt: Description of desired image
            negative_prompt: Description of what to avoid
            product_name: Product being marketed
            kol_persona: KOL/persona type
            image_type: Type of image
            run_id: Optional explicit run ID

        Returns:
            Dict containing execution metadata and GCS info
        """
        return await self.generate_and_wait(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            product_name=product_name,
            kol_persona=kol_persona,
            image_type=image_type,
            upload_to_gcs=getattr(GlobalConfig, "UPLOAD_GCS", True),
            run_id=run_id
        )


# Marketing prompt templates
MARKETING_PROMPTS = {
    "product_showcase": """
    Professional product photography of {product}, {style} style,
    clean background, perfect lighting, high resolution, commercial quality,
    {additional_details}
    """,

    "social_media": """
    Eye-catching social media post featuring {subject}, vibrant colors,
    modern aesthetic, {platform} optimized, engaging composition,
    {mood} mood, {additional_details}
    """,

    "lifestyle": """
    Lifestyle photography showing {product} in use, natural setting,
    authentic moments, aspirational but relatable, warm lighting,
    {demographic} demographic, {additional_details}
    """,

    "brand_hero": """
    Hero image for {brand}, premium quality, brand colors,
    minimalist design, professional photography, {industry} industry,
    {additional_details}
    """
}


def create_marketing_prompt(
    template_type: str,
    **kwargs
) -> str:
    """
    Create marketing-optimized prompts using templates.

    Args:
        template_type: Type of marketing content ('product_showcase', 'social_media', etc.)
        **kwargs: Template variables

    Returns:
        Formatted prompt string
    """
    if template_type not in MARKETING_PROMPTS:
        raise ValueError(f"Unknown template type: {template_type}")

    template = MARKETING_PROMPTS[template_type]

    try:
        return template.format(**kwargs).strip()
    except KeyError as e:
        raise ValueError(f"Missing required template variable: {e}")


# Global client instance
_client_instance = None

def get_client() -> ComfyUIClient:
    """Get singleton ComfyUI client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ComfyUIClient()
    return _client_instance
