import asyncio
import logging
from pathlib import Path

from backend.celery_app import celery_app
from backend.config import GlobalConfig
from backend.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from backend.third_parties.comfyui_client import ComfyUIClient
from backend.database.image_logs_storage import ImageLogsStorage
from backend.utils.constants import DEFAULT_NEGATIVE_PROMPT

logger = logging.getLogger(__name__)

_workflow = None
_client = None
_storage = None

# How often to re-check a pending ComfyUI execution (seconds)
DOWNLOAD_POLL_INTERVAL = int(GlobalConfig.COMFYUI_POLL_INTERVAL)
# Max retries before giving up (~1 hour at 5s intervals)
DOWNLOAD_MAX_RETRIES = int(GlobalConfig.COMFYUI_MAX_POLL_TIME) // DOWNLOAD_POLL_INTERVAL


def get_instances():
    global _workflow, _client, _storage
    if _workflow is None:
        _workflow = ImageToPromptWorkflow(verbose=False)
    if _client is None:
        _client = ComfyUIClient()
    if _storage is None:
        _storage = ImageLogsStorage()
    return _workflow, _client, _storage


def _review_queue_hook(execution_id: str, *, completed: bool,
                       result_path=None, error=None):
    """Best-effort: reflect a provider result onto the generation_requests
    row that dispatched it. Executions with no queue row (legacy, or logged
    outside the queue) are a no-op; hook errors never break the host task."""
    try:
        from backend.database.generation_requests_storage import GenerationRequestsStorage
        storage = GenerationRequestsStorage()
        if completed:
            storage.mark_completed_by_execution(execution_id, result_path)
        else:
            storage.mark_failed_by_execution(execution_id, error or "generation failed")
    except Exception as e:
        logger.warning(f"[review-hook] failed for {execution_id}: {e}")


@celery_app.task(
    bind=True,
    name="backend.tasks.download_execution_task",
    max_retries=DOWNLOAD_MAX_RETRIES,
    default_retry_delay=DOWNLOAD_POLL_INTERVAL,
)
def download_execution_task(self, execution_id: str, image_ref_path: str):
    """Check a single ComfyUI execution and download the result when ready.

    Uses Celery's retry mechanism so the worker is not blocked between checks.
    """
    _, client, storage = get_instances()
    output_dir = Path(GlobalConfig.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        status_data = asyncio.run(client.check_status(execution_id))
    except Exception as e:
        logger.error(f"[download_execution_task] Status check failed for {execution_id}: {e}")
        raise self.retry(exc=e, countdown=DOWNLOAD_POLL_INTERVAL)

    status = status_data.get("status")

    if status == "completed":
        output_images = status_data.get("output_images", [])
        comfy_image_paths = []
        if output_images and isinstance(output_images, list):
            for output in output_images:
                if isinstance(output, dict):
                    for _, paths in output.items():
                        if paths and isinstance(paths, list):
                            comfy_image_paths.extend(paths)

        if not comfy_image_paths:
            logger.warning(f"[download_execution_task] No output image paths found for {execution_id}")
            storage.mark_as_failed(execution_id)
            _review_queue_hook(execution_id, completed=False, error="no output images")
            return

        saved_paths = []
        base_name = Path(image_ref_path).stem if image_ref_path else execution_id

        for idx, comfy_image_path in enumerate(comfy_image_paths):
            try:
                image_bytes = asyncio.run(client.download_image_by_path(comfy_image_path))
            except Exception as e:
                logger.error(f"[download_execution_task] download_image_by_path failed for {execution_id} path {comfy_image_path}: {e}")
                if idx == 0:
                    try:
                        image_bytes = asyncio.run(client.download_image(execution_id))
                    except Exception as inner_e:
                        logger.error(f"[download_execution_task] Fallback download failed for {execution_id}: {inner_e}")
                        continue
                else:
                    continue

            suffix = f"_{idx}" if len(comfy_image_paths) > 1 else ""
            result_filename = f"result_{base_name}_{execution_id}{suffix}.png"
            local_result_path = output_dir / result_filename
            local_result_path.write_bytes(image_bytes)
            saved_paths.append(str(local_result_path))
            logger.info(f"[download_execution_task] ✅ Saved {local_result_path}")

        if not saved_paths:
            storage.mark_as_failed(execution_id)
            _review_queue_hook(execution_id, completed=False, error="no output images")
            return

        storage.update_result_path(
            execution_id=execution_id,
            result_image_path=",".join(saved_paths),
            new_ref_path=None,
        )
        _review_queue_hook(execution_id, completed=True, result_path=",".join(saved_paths))

    elif status == "failed":
        error_message = status_data.get("error_message", "Unknown ComfyUI error")
        logger.error(f"[download_execution_task] ❌ Execution {execution_id} failed: {error_message}")
        storage.mark_as_failed(execution_id)
        _review_queue_hook(execution_id, completed=False, error=error_message)

    else:
        # still running / queued — retry after interval
        raise self.retry(countdown=DOWNLOAD_POLL_INTERVAL)


@celery_app.task(bind=True, name="backend.tasks.process_image_task")
def process_image_task(
    self,
    dest_image_path,
    persona,
    workflow_type,
    vision_model,
    variation_count,
    strength_model,
    seed_strategy,
    base_seed,
    width,
    height,
    lora_name,
    clip_model_type="qwen_image",
    pipeline_type="image.subject_environment",
    workflow_overrides=None,
    workflow_name=None,
    project_id=None,
    created_by_member_id=None,
):
    """Celery task to run the CrewAI workflow and queue to ComfyUI."""
    try:
        self.update_state(state="STARTING", meta={"status": "⏳ Initializing task...", "progress": 10})
        return asyncio.run(
            async_process_image(
                dest_image_path=dest_image_path,
                persona=persona,
                workflow_type=workflow_type,
                vision_model=vision_model,
                variation_count=variation_count,
                strength_model=strength_model,
                seed_strategy=seed_strategy,
                base_seed=base_seed,
                width=width,
                height=height,
                lora_name=lora_name,
                clip_model_type=clip_model_type,
                pipeline_type=pipeline_type,
                workflow_overrides=workflow_overrides or {},
                workflow_name=workflow_name,
                project_id=project_id,
                created_by_member_id=created_by_member_id,
                task=self,
            )
        )
    except Exception as e:
        logger.error(f"Error in process_image_task for {dest_image_path}: {e}")
        raise e


async def async_process_image(
    dest_image_path, persona, workflow_type, vision_model, variation_count,
    strength_model, seed_strategy, base_seed, width, height, lora_name, clip_model_type,
    task, pipeline_type="image.subject_environment", workflow_overrides=None,
    workflow_name=None, project_id=None, created_by_member_id=None,
):
    workflow, client, storage = get_instances()

    logger.info(f"Generating {variation_count} prompt(s) for {dest_image_path}...")
    task.update_state(
        state="GENERATING_PROMPT",
        meta={"status": f"🤖 CrewAI analyzing image and writing {variation_count} prompt(s)...", "progress": 40},
    )

    try:
        result = await workflow.process(
            image_path=dest_image_path,
            persona_name=persona,
            workflow_type=workflow_type,
            vision_model=vision_model,
            variation_count=variation_count,
        )
    except Exception as e:
        error_msg = str(e)
        is_vision_refusal = "refused to analyze" in error_msg or "content policy" in error_msg.lower()
        is_empty_response = "Invalid response from LLM call - None or empty" in error_msg

        if is_vision_refusal or is_empty_response:
            if is_vision_refusal:
                label = f"Vision model refused: {error_msg}"
            else:
                label = (
                    "Agent Generation Failed: The AI returned an empty response. "
                    "Possible reasons: API Rate Limits/Timeouts, Safety filters, or Context length exceeded."
                )
            logger.error(f"[PROMPT FAILED] {label}")
            storage.log_failed_execution(
                image_ref_path=dest_image_path,
                error_message=label,
                persona=persona,
            )
            # Return instead of raise so Celery doesn't try to re-serialize the
            # exception on top of the FAILURE meta we already wrote, which causes
            # "Exception information must include the exception type".
            return {"success": False, "image_path": dest_image_path, "error": label}
        else:
            raise e

    prompts = result.get("generated_prompts", [result.get("generated_prompt")])
    logger.info(
        f"[PROMPT DEBUG] {len(prompts)} prompt(s) generated for {dest_image_path}:\n"
        + "\n".join(
            f"--- Variation {i+1} ({len(p)} chars) ---\n{p}"
            for i, p in enumerate(prompts)
        )
    )
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    task.update_state(
        state="QUEUEING_REVIEW",
        meta={"status": f"📋 Sending {len(prompts)} prompt(s) to the review queue...", "progress": 80},
    )

    settings = {
        "persona": persona,
        "workflow_type": workflow_type,
        "strength_model": strength_model,
        "seed_strategy": seed_strategy,
        "base_seed": base_seed,
        "width": width,
        "height": height,
        "lora_name": lora_name,
        "clip_model_type": clip_model_type,
        "pipeline_type": pipeline_type,
        "workflow_overrides": workflow_overrides or {},
        "negative_prompt": DEFAULT_NEGATIVE_PROMPT,
    }
    created = GenerationRequestsStorage().create_requests(
        [
            {
                "source_image_path": dest_image_path,
                "prompt": prompt_content,
                "provider": "comfy_image",
                "workflow_name": workflow_name,
                "settings": settings,
            }
            for prompt_content in prompts
        ],
        project_id=project_id,
        created_by_member_id=created_by_member_id,
    )

    task.update_state(
        state="SUCCESS",
        meta={"status": f"✅ {len(prompts)} prompt(s) awaiting review for {dest_image_path}", "progress": 100},
    )

    return {
        "success": True,
        "image_path": dest_image_path,
        "queued_for_review": len(prompts),
        "total_variations": len(prompts),
        "batch_id": created["batch_id"],
        "request_ids": created["request_ids"],
    }


@celery_app.task(bind=True, name="backend.tasks.caption_export_task")
def caption_export_task(
    self,
    image_entries: list,  # [{stem, path, original_ext}]
    persona: str,
    vision_model: str,
    workflow_type: str = "turbo",
):
    """Run CrewAI on each image and return prompts. Does NOT send to ComfyUI."""
    workflow, _, _ = get_instances()
    results = []
    total = len(image_entries)

    for i, entry in enumerate(image_entries):
        self.update_state(
            state="PROGRESS",
            meta={
                "status": f"🤖 Captioning {i + 1}/{total}: {entry['stem']}",
                "progress": int(100 * i / total),
            },
        )
        try:
            result = asyncio.run(
                workflow.process(
                    image_path=entry["path"],
                    persona_name=persona,
                    workflow_type=workflow_type,
                    vision_model=vision_model,
                    variation_count=1,
                )
            )
            prompts = result.get("generated_prompts", [result.get("generated_prompt", "")])
            prompt = prompts[0] if prompts else ""
            results.append({
                "stem": entry["stem"],
                "path": entry["path"],
                "original_ext": entry["original_ext"],
                "prompt": prompt,
                "success": True,
            })
        except Exception as e:
            logger.error(f"[caption_export_task] Failed for {entry['stem']}: {e}")
            results.append({
                "stem": entry["stem"],
                "path": entry["path"],
                "original_ext": entry["original_ext"],
                "prompt": "",
                "error": str(e),
                "success": False,
            })

    succeeded = sum(1 for r in results if r["success"])
    return {
        "results": results,
        "total": total,
        "status": f"✅ Captioned {succeeded}/{total} images",
    }


@celery_app.task(bind=True, name="backend.tasks.merge_videos_task")
def merge_videos_task(self, filenames: list, transition_type: str, transition_duration: float):
    """Merge multiple videos with transitions."""
    from backend.config import GlobalConfig
    from backend.utils.video_utils import merge_videos
    from pathlib import Path
    import uuid

    video_dir = Path(GlobalConfig.VIDEO_DIR)
    video_paths = [str(video_dir / f) for f in filenames]
    output_filename = f"merged_{uuid.uuid4().hex[:8]}.mp4"
    output_path = str(video_dir / output_filename)

    def progress_cb(p):
        self.update_state(state="PROGRESS", meta={"progress": int(p * 100)})

    merge_videos(video_paths, output_path, transition_type, transition_duration, progress_cb)
    return {"output_filename": output_filename, "output_path": output_path}


@celery_app.task(bind=True, name="backend.tasks.analyze_music_task")
def analyze_music_task(self, audio_path: str):
    """Run music analysis workflow on an audio file."""
    from backend.workflows.music_analysis_workflow import MusicAnalysisWorkflow

    self.update_state(state="PROGRESS", meta={"status": "Analyzing audio...", "progress": 20})
    workflow = MusicAnalysisWorkflow(verbose=False)
    result = workflow.process(audio_path)
    return {"vibe": result.get("vibe", ""), "lyrics": result.get("lyrics", ""), "analysis": str(result)}


@celery_app.task(bind=True, name="backend.tasks.generate_storyboard_task")
def generate_storyboard_task(
    self,
    image_paths: list,
    persona: str,
    vision_model: str,
    variation_count: int,
):
    """Run VideoStoryboardWorkflow for a list of images and return combined results."""
    from backend.services.video import VideoService

    svc = VideoService()
    results = []
    total = len(image_paths)
    for i, image_path in enumerate(image_paths):
        self.update_state(
            state="PROGRESS",
            meta={"status": f"Processing image {i + 1}/{total}", "progress": int(100 * i / total)},
        )
        result = svc.generate_storyboard(
            image_path=image_path,
            persona=persona,
            vision_model=vision_model,
            variation_count=variation_count,
        )
        results.append(result)
    return {"results": results}


@celery_app.task(
    bind=True,
    name="backend.tasks.poll_comfy_video_task",
    max_retries=120,
    default_retry_delay=10,
)
def poll_comfy_video_task(self, prompt_id: str, image_path: str, batch_id=None):
    """
    Poll ComfyUI for a Kling video job and download the result when complete.
    Retries every 10 seconds for up to 20 minutes.
    """
    import asyncio
    from pathlib import Path
    from backend.third_parties.comfyui_client import ComfyUIClient
    from backend.database.video_logs_storage import VideoLogsStorage
    from backend.config import GlobalConfig

    client = ComfyUIClient()
    video_dir = Path(GlobalConfig.VIDEO_DIR)
    video_dir.mkdir(parents=True, exist_ok=True)
    storage = VideoLogsStorage()

    try:
        status_data = asyncio.run(client.check_video_status(prompt_id))
    except Exception as e:
        logger.error(f"[poll_comfy_video_task] Status check failed for {prompt_id}: {e}")
        raise self.retry(exc=e)

    status = status_data.get("status")

    if status == "completed":
        # Try to find the output video path
        output_videos = status_data.get("output_videos", [])
        output_path = None

        if output_videos:
            for node_output in output_videos:
                for node_id, paths in node_output.items():
                    if paths:
                        video_file_path = paths[0]
                        try:
                            video_bytes = asyncio.run(client.download_file_by_path(video_file_path))
                            local_filename = f"comfy_{prompt_id}.mp4"
                            local_path = video_dir / local_filename
                            local_path.write_bytes(video_bytes)
                            output_path = str(local_path)
                            logger.info(f"[poll_comfy_video_task] Downloaded ComfyUI video to {local_path}")
                        except Exception as e:
                            logger.error(f"[poll_comfy_video_task] Download failed for {prompt_id}: {e}")
                        break
                if output_path:
                    break

        storage.update_result(
            execution_id=prompt_id,
            video_output_path=output_path,
            status="completed",
        )
        _review_queue_hook(prompt_id, completed=True, result_path=output_path)

    elif status == "failed":
        error_message = status_data.get("error_message", "Unknown ComfyUI error")
        logger.error(f"[poll_comfy_video_task] ComfyUI job {prompt_id} failed: {error_message}")
        storage.update_result(execution_id=prompt_id, status="failed")
        _review_queue_hook(prompt_id, completed=False, error=error_message)

    else:
        # Still running — retry
        raise self.retry()


@celery_app.task(bind=True, name="backend.tasks.dispatch_generation_request_task")
def dispatch_generation_request_task(self, request_id: str):
    """Send ONE approved generation_requests row to its provider.

    Returns instead of raising on provider errors so a failure affects only
    this item (the rest of a dispatched selection proceeds), matching the
    phase-2 spec. begin_dispatch() is the idempotency guard: a redelivered
    task finds the row already 'dispatched' and no-ops.
    """
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    storage = GenerationRequestsStorage()
    row = storage.begin_dispatch(request_id)
    if row is None:
        logger.info(f"[dispatch] {request_id} not in 'approved' state — skipping")
        return {"request_id": request_id, "skipped": True}

    provider = row["provider"]
    settings = row["settings"] or {}
    try:
        if provider == "comfy_image":
            _, client, image_storage = get_instances()
            execution_id = asyncio.run(client.generate_image(
                positive_prompt=row["prompt"],
                negative_prompt=settings.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT),
                kol_persona=settings.get("persona"),
                workflow_type=settings.get("workflow_type"),
                strength_model=settings.get("strength_model"),
                seed_strategy=settings.get("seed_strategy"),
                base_seed=settings.get("base_seed"),
                width=settings.get("width"),
                height=settings.get("height"),
                lora_name=settings.get("lora_name"),
                clip_model_type=settings.get("clip_model_type", "qwen_image"),
                pipeline_type=settings.get("pipeline_type", "image.subject_environment"),
                workflow_overrides=settings.get("workflow_overrides") or {},
                workflow_name=row["workflow_name"],
            ))
            if not execution_id:
                raise RuntimeError("ComfyUI returned no execution id")
            image_storage.log_execution(
                execution_id=execution_id,
                prompt=row["prompt"],
                image_ref_path=row["source_image_path"],
                persona=settings.get("persona"),
                project_id=row.get("project_id"),
                created_by_member_id=row.get("created_by_member_id"),
            )
            download_execution_task.apply_async(
                args=[execution_id, row["source_image_path"]],
                countdown=DOWNLOAD_POLL_INTERVAL,
                queue="image",
            )
        elif provider == "kling":
            from backend.services.video import VideoService
            from backend.models.video import KlingSettings
            execution_id = VideoService().queue_video(
                image_path=row["source_image_path"],
                prompt=row["prompt"],
                kling_settings=KlingSettings(**settings),
                batch_id=row["batch_id"],
                project_id=row.get("project_id"),
                created_by_member_id=row.get("created_by_member_id"),
            )
        elif provider == "comfy_video":
            from backend.services.video import VideoService
            from backend.models.video import ComfyKlingSettings
            execution_id = VideoService().queue_video_comfy(
                image_path=row["source_image_path"],
                prompt=row["prompt"],
                comfy_settings=ComfyKlingSettings(**settings),
                batch_id=row["batch_id"],
                project_id=row.get("project_id"),
                created_by_member_id=row.get("created_by_member_id"),
            )
        else:
            raise ValueError(f"Unknown provider {provider!r}")

        storage.set_execution(request_id, execution_id)
        return {"request_id": request_id, "execution_id": execution_id}
    except Exception as e:
        logger.error(f"[dispatch] {request_id} ({provider}) failed: {e}")
        storage.mark_failed(request_id, str(e))
        return {"request_id": request_id, "error": str(e)}


@celery_app.task(
    bind=True,
    name="backend.tasks.poll_kling_video_task",
    max_retries=120,
    default_retry_delay=10,
)
def poll_kling_video_task(self, task_id: str):
    """Poll the Kling API until a video task reaches a terminal state.

    VideoService.get_video_status() already downloads the file and updates
    video_logs; this task exists so completion does not depend on a browser
    polling the status endpoint. (Fixes the pre-existing phantom import in
    VideoService.queue_video — this task never existed.)
    """
    from backend.services.video import VideoService

    status = VideoService().get_video_status(task_id)
    if status.status == "completed":
        return {"task_id": task_id, "status": "completed"}
    if status.status in ("failed", "error"):
        logger.error(f"[poll_kling_video_task] {task_id} -> {status.status}: {status.error_message}")
        return {"task_id": task_id, "status": status.status}
    raise self.retry()
