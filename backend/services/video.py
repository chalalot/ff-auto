"""
VideoService — backend service for Kling video generation, storyboarding,
music analysis, video merging, and preset management.
"""
import io
import json
import logging
import math
import os
from pathlib import Path
from typing import List, Optional

from backend.config import GlobalConfig
from backend.database.video_logs_storage import VideoLogsStorage
from backend.models.video import KlingPreset, KlingSettings, VideoItem, VideoStatusResponse
from backend.third_parties.kling_client import KlingClient

logger = logging.getLogger(__name__)


class VideoService:
    def __init__(self):
        self.video_dir = Path(GlobalConfig.VIDEO_DIR)
        self.video_dir.mkdir(parents=True, exist_ok=True)

        self.storage = VideoLogsStorage(str(self.video_dir / "video_logs.db"))
        self.kling_client = KlingClient()
        self.presets_path = self.video_dir / "kling_presets.json"

    # ------------------------------------------------------------------
    # Storyboard
    # ------------------------------------------------------------------

    def generate_storyboard(
        self,
        image_path: str,
        persona: str,
        vision_model: str = "gpt-4o",
        variation_count: int = 3,
    ) -> dict:
        """Run VideoStoryboardWorkflow for a single image."""
        from backend.workflows.video_storyboard_workflow import VideoStoryboardWorkflow

        workflow = VideoStoryboardWorkflow(verbose=False, vision_model=vision_model)
        result = workflow.process(image_path, persona, variation_count)
        return result

    # ------------------------------------------------------------------
    # Video generation
    # ------------------------------------------------------------------

    def queue_video(
        self,
        image_path: str,
        prompt: Optional[str],
        kling_settings: KlingSettings,
        batch_id: Optional[str] = None,
    ) -> str:
        """Queue a video generation task on Kling and log it to DB."""
        task_id = self.kling_client.generate_video(
            prompt=prompt or "",
            image=image_path,
            model_name=kling_settings.model_name,
            mode=kling_settings.mode,
            duration=kling_settings.duration,
            aspect_ratio=kling_settings.aspect_ratio,
            cfg_scale=kling_settings.cfg_scale,
            negative_prompt=kling_settings.negative_prompt,
            sound=kling_settings.sound,
            voice_list=kling_settings.voice_list,
        )

        self.storage.log_execution(
            execution_id=task_id,
            prompt=prompt or "",
            source_image_path=image_path,
            batch_id=batch_id,
        )

        logger.info(f"[VideoService] Queued Kling task {task_id} for {image_path}")
        return task_id

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    def get_video_status(self, task_id: str) -> VideoStatusResponse:
        """Poll Kling for task status; download video when complete."""
        try:
            result = self.kling_client.get_video_status(task_id)
        except Exception as e:
            logger.error(f"[VideoService] get_video_status failed for {task_id}: {e}")
            return VideoStatusResponse(task_id=task_id, status="error")

        kling_status = result.get("task_status", "unknown")
        video_url = result.get("video_url")
        duration = result.get("duration")

        local_path = None

        if kling_status == "succeed" and video_url:
            local_file = self.video_dir / f"{task_id}.mp4"
            if not local_file.exists():
                try:
                    self.kling_client.download_video(video_url, str(local_file))
                    self.storage.update_result(task_id, str(local_file), "completed")
                    logger.info(f"[VideoService] Downloaded video to {local_file}")
                except Exception as e:
                    logger.error(f"[VideoService] Download failed for {task_id}: {e}")
            local_path = str(local_file) if local_file.exists() else None

        # Map Kling status to internal status
        status_map = {
            "succeed": "completed",
            "processing": "processing",
            "submitted": "pending",
            "failed": "failed",
        }
        status = status_map.get(kling_status, kling_status)

        return VideoStatusResponse(
            task_id=task_id,
            status=status,
            progress=100 if status == "completed" else 50 if status == "processing" else 0,
            video_url=video_url,
            local_path=local_path,
            duration=str(duration) if duration is not None else None,
        )

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_videos(self, page: int = 1, per_page: int = 20) -> dict:
        """Paginate video execution records from DB."""
        all_records = self.storage.get_recent_executions(limit=1000)
        total = len(all_records)
        pages = math.ceil(total / per_page) if total else 1
        page = max(1, min(page, pages))

        start = (page - 1) * per_page
        end = start + per_page
        slice_ = all_records[start:end]

        items: List[VideoItem] = []
        for rec in slice_:
            video_output_path = rec.get("video_output_path")
            filename = Path(video_output_path).name if video_output_path else None
            thumbnail_url = f"/api/video/{filename}/thumbnail" if filename else None

            items.append(
                VideoItem(
                    id=rec.get("id", 0),
                    execution_id=rec.get("execution_id", ""),
                    filename=filename,
                    source_image=rec.get("source_image_path"),
                    prompt=rec.get("prompt", ""),
                    status=rec.get("status", "pending"),
                    created_at=str(rec.get("created_at", "")),
                    batch_id=rec.get("batch_id"),
                    video_url=None,
                    thumbnail_url=thumbnail_url,
                )
            )

        return {
            "items": [item.model_dump() for item in items],
            "total": total,
            "page": page,
            "pages": pages,
        }

    # ------------------------------------------------------------------
    # Thumbnail
    # ------------------------------------------------------------------

    def get_video_thumbnail(self, filename: str) -> Optional[bytes]:
        """Extract the first frame of a video file and return as JPEG bytes."""
        video_path = self.video_dir / filename
        if not video_path.exists():
            return None

        # Try cv2 first (fast)
        try:
            import cv2

            cap = cv2.VideoCapture(str(video_path))
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                import cv2 as _cv2

                _, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, 85])
                return buf.tobytes()
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[VideoService] cv2 thumbnail failed for {filename}: {e}")

        # PIL/Pillow fallback via moviepy
        try:
            from moviepy import VideoFileClip

            with VideoFileClip(str(video_path)) as clip:
                frame = clip.get_frame(0)
                from PIL import Image

                img = Image.fromarray(frame)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
        except Exception as e:
            logger.warning(f"[VideoService] moviepy thumbnail failed for {filename}: {e}")

        return None

    # ------------------------------------------------------------------
    # Merge (sync wrapper — called from Celery task)
    # ------------------------------------------------------------------

    def merge_videos_sync(
        self,
        filenames: List[str],
        transition_type: str = "Crossfade",
        transition_duration: float = 0.5,
    ) -> str:
        """Merge video files and return the output filename."""
        from backend.utils import video_utils
        import uuid

        video_paths = [str(self.video_dir / f) for f in filenames]
        output_filename = f"merged_{uuid.uuid4().hex[:8]}.mp4"
        output_path = str(self.video_dir / output_filename)

        video_utils.merge_videos(video_paths, output_path, transition_type, transition_duration)
        return output_filename

    # ------------------------------------------------------------------
    # Music analysis
    # ------------------------------------------------------------------

    def analyze_music(self, audio_path: str) -> dict:
        """Run music analysis workflow and return vibe + lyrics."""
        from backend.workflows.music_analysis_workflow import MusicAnalysisWorkflow

        workflow = MusicAnalysisWorkflow(verbose=False)
        result = workflow.process(audio_path)
        return {
            "vibe": result.get("vibe", ""),
            "lyrics": result.get("lyrics", ""),
            "analysis": str(result),
        }

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def _load_presets(self) -> dict:
        if self.presets_path.exists():
            try:
                return json.loads(self.presets_path.read_text())
            except Exception:
                return {}
        return {}

    def _save_presets(self, presets: dict) -> None:
        self.presets_path.write_text(json.dumps(presets, indent=2))

    def list_presets(self) -> List[dict]:
        presets = self._load_presets()
        return [
            {"name": name, "settings": settings}
            for name, settings in presets.items()
        ]

    def save_preset(self, name: str, settings: KlingSettings) -> dict:
        presets = self._load_presets()
        presets[name] = settings.model_dump()
        self._save_presets(presets)
        return {"name": name, "settings": settings.model_dump()}

    def delete_preset(self, name: str) -> bool:
        presets = self._load_presets()
        if name not in presets:
            return False
        del presets[name]
        self._save_presets(presets)
        return True
