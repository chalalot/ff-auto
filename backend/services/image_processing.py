"""
ImageProcessingService — extracted from 1_workspace_app.py

Handles: input directory scanning, image preparation (copy+rename),
Celery task dispatch, task status polling.
"""
import os
import shutil
import uuid
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from celery.result import AsyncResult

from backend.config import GlobalConfig
from backend.celery_app import celery_app

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ImageProcessingService:
    def __init__(self):
        self.input_dir = Path(GlobalConfig.INPUT_DIR)
        self.processed_dir = Path(GlobalConfig.PROCESSED_DIR)
        self.output_dir = Path(GlobalConfig.OUTPUT_DIR)

        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Input directory scanning
    # ------------------------------------------------------------------

    def scan_input_directory(self) -> List[dict]:
        """List images in INPUT_DIR sorted by mtime descending."""
        results = []
        try:
            with os.scandir(self.input_dir) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    try:
                        stat = entry.stat()
                        results.append(
                            {
                                "filename": entry.name,
                                "path": str(entry.path),
                                "size_bytes": stat.st_size,
                                "modified_at": stat.st_mtime,
                                "thumbnail_url": f"/api/workspace/input-images/{entry.name}/thumbnail",
                            }
                        )
                    except OSError:
                        continue
        except OSError as e:
            logger.error(f"Error scanning input dir: {e}")

        results.sort(key=lambda x: x["modified_at"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Image preparation
    # ------------------------------------------------------------------

    def prepare_image(self, src_path: str) -> str:
        """
        Copy an input image to PROCESSED_DIR with a unique ref_ name.
        Returns the destination path.
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Source image not found: {src_path}")

        timestamp = int(time.time())
        unique_id = uuid.uuid4().hex[:8]
        dest_name = f"ref_{timestamp}_{unique_id}{src.suffix.lower()}"
        dest_path = self.processed_dir / dest_name
        shutil.copy2(src, dest_path)
        logger.info(f"Prepared image: {src} → {dest_path}")
        return str(dest_path)

    # ------------------------------------------------------------------
    # Celery dispatch
    # ------------------------------------------------------------------

    def dispatch_processing(
        self,
        image_path: str,
        persona: str,
        workflow_type: str = "turbo",
        vision_model: str = "gpt-4o",
        variation_count: int = 1,
        strength: float = 0.8,
        seed_strategy: str = "random",
        base_seed: int = 0,
        width: int = 1024,
        height: int = 1600,
        lora_name: str = "",
        clip_model_type: str = "sd3",
        prepare: bool = True,
    ) -> str:
        """
        Prepare the image and dispatch a Celery task.
        Returns the Celery task_id.
        """
        dest_path = self.prepare_image(image_path) if prepare else image_path

        task = celery_app.send_task(
            "backend.tasks.process_image_task",
            kwargs={
                "dest_image_path": dest_path,
                "persona": persona,
                "workflow_type": workflow_type,
                "vision_model": vision_model,
                "variation_count": variation_count,
                "strength_model": strength,
                "seed_strategy": seed_strategy,
                "base_seed": base_seed,
                "width": width,
                "height": height,
                "lora_name": lora_name,
                "clip_model_type": clip_model_type,
            },
        )
        logger.info(f"Dispatched task {task.id} for {dest_path}")
        return task.id

    def dispatch_batch(self, image_paths: List[str], **kwargs) -> List[str]:
        """Dispatch processing for multiple images. Returns list of task IDs."""
        task_ids = []
        for path in image_paths:
            task_id = self.dispatch_processing(image_path=path, **kwargs)
            task_ids.append(task_id)
        return task_ids

    # ------------------------------------------------------------------
    # Task status
    # ------------------------------------------------------------------

    def get_task_status(self, task_id: str) -> dict:
        """Wrap AsyncResult into a clean dict."""
        try:
            result = AsyncResult(task_id, app=celery_app)
            # Access state first — this triggers backend deserialization
            state = result.state
            info = result.info or {}
        except Exception:
            # Stale/corrupt result in Redis (e.g. from a different Celery version)
            return {
                "task_id": task_id,
                "state": "PENDING",
                "status_message": "Waiting...",
                "progress": 0,
                "result": None,
            }

        if state in ("PENDING", "STARTED", "RETRY"):
            return {
                "task_id": task_id,
                "state": state,
                "status_message": info.get("status", ""),
                "progress": info.get("progress", 0),
                "result": None,
            }
        elif state == "FAILURE":
            return {
                "task_id": task_id,
                "state": "FAILURE",
                "status_message": str(info) if info else "Task failed",
                "progress": 0,
                "result": None,
            }
        elif state == "SUCCESS":
            return {
                "task_id": task_id,
                "state": "SUCCESS",
                "status_message": info.get("status", "✅ Done"),
                "progress": 100,
                "result": result.result,
            }
        else:
            # Custom states: STARTING, GENERATING_PROMPT, QUEUEING_COMFY
            return {
                "task_id": task_id,
                "state": result.state,
                "status_message": info.get("status", ""),
                "progress": info.get("progress", 0),
                "result": None,
            }

    # ------------------------------------------------------------------
    # Input image thumbnail (served directly)
    # ------------------------------------------------------------------

    def get_input_image_thumbnail(self, filename: str) -> Optional[bytes]:
        """Generate or return cached thumbnail for an input image."""
        from PIL import Image
        import io

        original_path = self.input_dir / filename
        if not original_path.exists():
            return None

        thumb_dir = self.input_dir / ".thumbnails"
        thumb_dir.mkdir(exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{filename}"

        if thumb_path.exists() and thumb_path.stat().st_mtime >= original_path.stat().st_mtime:
            return thumb_path.read_bytes()

        try:
            with Image.open(original_path) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                data = buf.getvalue()
                thumb_path.write_bytes(data)
                return data
        except Exception as e:
            logger.error(f"Thumbnail generation failed for {filename}: {e}")
            return None
