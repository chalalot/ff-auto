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
        comfy_image_path = None
        if output_images and isinstance(output_images, list):
            first_output = output_images[0]
            if isinstance(first_output, dict):
                for _, paths in first_output.items():
                    if paths:
                        comfy_image_path = paths[0]
                        break

        if not comfy_image_path:
            logger.warning(f"[download_execution_task] No output image path for {execution_id}")
            storage.mark_as_failed(execution_id)
            return

        try:
            image_bytes = asyncio.run(client.download_image_by_path(comfy_image_path))
        except Exception as e:
            logger.error(f"[download_execution_task] download_image_by_path failed for {execution_id}: {e}")
            try:
                image_bytes = asyncio.run(client.download_image(execution_id))
            except Exception as inner_e:
                logger.error(f"[download_execution_task] Fallback download failed for {execution_id}: {inner_e}")
                storage.mark_as_failed(execution_id)
                return

        base_name = Path(image_ref_path).stem if image_ref_path else execution_id
        result_filename = f"result_{base_name}_{execution_id}.png"
        local_result_path = output_dir / result_filename
        local_result_path.write_bytes(image_bytes)

        storage.update_result_path(
            execution_id=execution_id,
            result_image_path=str(local_result_path),
            new_ref_path=None,
        )
        logger.info(f"[download_execution_task] ✅ Saved {local_result_path}")

    elif status == "failed":
        logger.error(f"[download_execution_task] ❌ Execution {execution_id} failed.")
        storage.mark_as_failed(execution_id)

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
    clip_model_type="sd3",
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
                task=self,
            )
        )
    except Exception as e:
        logger.error(f"Error in process_image_task for {dest_image_path}: {e}")
        raise e


async def async_process_image(
    dest_image_path, persona, workflow_type, vision_model, variation_count,
    strength_model, seed_strategy, base_seed, width, height, lora_name, clip_model_type, task
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
    successful_queues_for_image = 0
    execution_ids = []

    for i, prompt_content in enumerate(prompts):
        logger.info(f"Queueing execution for {dest_image_path} (Variation {i+1}/{len(prompts)})...")
        prog = int(60 + (30 * (i / len(prompts))))
        task.update_state(
            state="QUEUEING_COMFY",
            meta={"status": f"🎨 Sending variation {i+1}/{len(prompts)} to ComfyUI...", "progress": prog},
        )

        execution_id = await client.generate_image(
            positive_prompt=prompt_content,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            kol_persona=persona,
            workflow_type=workflow_type,
            strength_model=strength_model,
            seed_strategy=seed_strategy,
            base_seed=base_seed,
            width=width,
            height=height,
            lora_name=lora_name,
            clip_model_type=clip_model_type,
        )

        if execution_id:
            logger.info(f"✅ Queued Variation {i+1} - Execution ID: {execution_id}")
            storage.log_execution(
                execution_id=execution_id,
                prompt=prompt_content,
                image_ref_path=dest_image_path,
                persona=persona,
            )
            download_execution_task.apply_async(
                args=[execution_id, dest_image_path],
                countdown=DOWNLOAD_POLL_INTERVAL,
            )
            successful_queues_for_image += 1
            execution_ids.append(execution_id)
        else:
            logger.error(f"Failed to get execution ID for variation {i+1}.")

    task.update_state(
        state="SUCCESS",
        meta={"status": f"✅ Finished processing {dest_image_path}", "progress": 100},
    )

    return {
        "success": True,
        "image_path": dest_image_path,
        "queued_variations": successful_queues_for_image,
        "total_variations": len(prompts),
        "execution_ids": execution_ids,
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
