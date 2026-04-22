"""
ImageProcessingService — extracted from 1_workspace_app.py

Handles: input directory scanning, image preparation (copy+rename),
Celery task dispatch, task status polling.
"""
import os
import json
import shutil
import uuid
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import redis as _redis
from celery.result import AsyncResult

from backend.config import GlobalConfig
from backend.celery_app import celery_app

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Redis keys for cross-user task visibility
_ACTIVE_TASKS_SET = "ff_auto:active_tasks"   # Redis Set of task_ids
_TASK_META_PREFIX = "ff_auto:task_meta:"     # Redis String (JSON) per task
_TASK_META_TTL = 6 * 3600                    # 6 hours TTL


def _redis_client() -> _redis.Redis:
    url = celery_app.conf.broker_url
    return _redis.from_url(url, decode_responses=True)


class ImageProcessingService:
    def __init__(self):
        self.input_dir = Path(GlobalConfig.INPUT_DIR).resolve()
        self.processed_dir = Path(GlobalConfig.PROCESSED_DIR).resolve()
        self.output_dir = Path(GlobalConfig.OUTPUT_DIR).resolve()

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
            queue="image",
        )
        logger.info(f"Dispatched task {task.id} for {dest_path}")

        # Register in Redis so all users can see this task
        try:
            r = _redis_client()
            meta = json.dumps({
                "image_path": dest_path,
                "persona": persona,
                "dispatched_at": time.time(),
            })
            r.sadd(_ACTIVE_TASKS_SET, task.id)
            r.setex(_TASK_META_PREFIX + task.id, _TASK_META_TTL, meta)
        except Exception as e:
            logger.warning(f"Could not register task {task.id} in Redis: {e}")

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

    def get_active_tasks(self) -> List[dict]:
        """
        Return all tasks currently registered in Redis (dispatched but not yet
        completed). Automatically prunes tasks that have reached a terminal state.
        Any user who calls this endpoint sees every running task, not just their own.
        """
        try:
            r = _redis_client()
            task_ids = r.smembers(_ACTIVE_TASKS_SET)
        except Exception as e:
            logger.error(f"Redis error fetching active tasks: {e}")
            return []

        tasks = []
        for tid in task_ids:
            try:
                result = AsyncResult(tid, app=celery_app)
                state = result.state

                if state in ("SUCCESS", "FAILURE", "REVOKED"):
                    # Prune from registry — task is done
                    r.srem(_ACTIVE_TASKS_SET, tid)
                    r.delete(_TASK_META_PREFIX + tid)
                    continue

                meta_raw = r.get(_TASK_META_PREFIX + tid)
                meta = json.loads(meta_raw) if meta_raw else {}
                info = result.info or {}

                tasks.append({
                    "task_id": tid,
                    "state": state,
                    "status_message": info.get("status", ""),
                    "progress": info.get("progress", 0),
                    "image_path": meta.get("image_path"),
                    "persona": meta.get("persona", ""),
                    "dispatched_at": meta.get("dispatched_at"),
                    "task_type": meta.get("task_type", "image_process"),
                    "image_count": meta.get("image_count"),
                })
            except Exception as e:
                logger.error(f"Error reading task {tid}: {e}")

        tasks.sort(key=lambda x: x.get("dispatched_at") or 0, reverse=True)
        return tasks

    # ------------------------------------------------------------------
    # Reference image library (processed/ directory)
    # ------------------------------------------------------------------

    def scan_ref_images(self, use_counts: dict) -> List[dict]:
        """List images in PROCESSED_DIR with use counts from DB."""
        results = []
        try:
            with os.scandir(self.processed_dir) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    try:
                        stat = entry.stat()
                        count = use_counts.get(str(entry.path), 0)
                        results.append({
                            "filename": entry.name,
                            "path": str(entry.path),
                            "size_bytes": stat.st_size,
                            "modified_at": stat.st_mtime,
                            "thumbnail_url": f"/api/workspace/ref-images/{entry.name}/thumbnail",
                            "use_count": count,
                            "is_used": count > 0,
                        })
                    except OSError:
                        continue
        except OSError as e:
            logger.error(f"Error scanning processed dir: {e}")
        results.sort(key=lambda x: x["modified_at"], reverse=True)
        return results

    def save_ref_image(self, filename: str, data: bytes) -> str:
        """Save image bytes directly to PROCESSED_DIR with ref_ prefix. Returns dest path."""
        ext = Path(filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")
        timestamp = int(time.time())
        unique_id = uuid.uuid4().hex[:8]
        dest_name = f"ref_{timestamp}_{unique_id}{ext}"
        dest_path = self.processed_dir / dest_name
        dest_path.write_bytes(data)
        logger.info(f"Saved ref image: {dest_path}")
        return str(dest_path)

    def delete_ref_image(self, filename: str) -> None:
        """Delete a ref image from PROCESSED_DIR. Also removes its thumbnail cache."""
        target = self.processed_dir / filename
        if not target.exists():
            raise FileNotFoundError(f"Ref image not found: {filename}")
        target.unlink()
        thumb = self.processed_dir / ".thumbnails" / f"thumb_{filename}"
        if thumb.exists():
            thumb.unlink()
        logger.info(f"Deleted ref image: {filename}")

    def get_ref_image_thumbnail(self, filename: str) -> Optional[bytes]:
        """Generate or return cached thumbnail for a ref image."""
        from PIL import Image
        import io

        original_path = self.processed_dir / filename
        if not original_path.exists():
            return None

        thumb_dir = self.processed_dir / ".thumbnails"
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
            logger.error(f"Ref image thumbnail failed for {filename}: {e}")
            return None

    def get_ref_image_bytes(self, filename: str) -> Optional[bytes]:
        """Return raw bytes of a ref image."""
        path = self.processed_dir / filename
        if not path.exists():
            return None
        return path.read_bytes()

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
