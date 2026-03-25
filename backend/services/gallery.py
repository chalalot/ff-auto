"""
GalleryService — extracted from 2_gallery_app.py

Handles: image listing/pagination, thumbnail generation, metadata extraction,
approve/disapprove/undo file moves, stats, ZIP download, daily notes.
"""
import io
import json
import logging
import math
import os
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from PIL import Image

from backend.config import GlobalConfig
from backend.database.image_logs_storage import ImageLogsStorage

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class GalleryService:
    def __init__(self):
        self.output_dir = Path(GlobalConfig.OUTPUT_DIR)
        self.approved_dir = self.output_dir / "approved"
        self.disapproved_dir = self.output_dir / "disapproved"
        self.thumbnails_dir = self.output_dir / ".thumbnails"

        for d in (self.output_dir, self.approved_dir, self.disapproved_dir, self.thumbnails_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.storage = ImageLogsStorage()
        self.notes_file = self.output_dir / "daily_notes.json"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dir_for_status(self, status: str) -> Path:
        if status == "approved":
            return self.approved_dir
        if status == "disapproved":
            return self.disapproved_dir
        return self.output_dir

    def _scan_dir(self, directory: Path) -> List[tuple]:
        """Scan directory, returning [(filename, mtime)] sorted newest first."""
        results = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    try:
                        results.append((entry.name, entry.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            pass
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Listing & pagination
    # ------------------------------------------------------------------

    def list_images(
        self,
        status: str = "pending",
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        directory = self._dir_for_status(status)
        all_files = self._scan_dir(directory)
        total = len(all_files)
        pages = math.ceil(total / per_page) if total else 1
        page = max(1, min(page, pages))

        start = (page - 1) * per_page
        end = start + per_page
        slice_ = all_files[start:end]

        items = []
        for filename, mtime in slice_:
            dt = datetime.fromtimestamp(mtime)
            items.append(
                {
                    "filename": filename,
                    "path": str(directory / filename),
                    "thumbnail_url": f"/api/gallery/images/{filename}/thumbnail?status={status}",
                    "created_at": mtime,
                    "date": dt.strftime("%Y-%m-%d"),
                }
            )

        return {"items": items, "total": total, "page": page, "pages": pages, "per_page": per_page}

    # ------------------------------------------------------------------
    # Thumbnail
    # ------------------------------------------------------------------

    def get_thumbnail(self, filename: str, status: str = "pending") -> Optional[bytes]:
        original_path = self._dir_for_status(status) / filename
        if not original_path.exists():
            return None

        thumb_path = self.thumbnails_dir / f"thumb_{filename}"
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

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------

    def extract_metadata(self, filename: str, status: str = "pending") -> dict:
        path = self._dir_for_status(status) / filename
        metadata = {"seed": None, "prompt": None, "persona": None, "ref_image": None, "raw_metadata": {}}

        try:
            with Image.open(path) as img:
                meta = img.info
                if "prompt" in meta:
                    prompt_data = json.loads(meta["prompt"])
                    metadata["raw_metadata"] = prompt_data
                    for node_id, node_data in prompt_data.items():
                        inputs = node_data.get("inputs", {})
                        class_type = node_data.get("class_type", "")
                        if metadata["seed"] is None:
                            if "seed" in inputs:
                                metadata["seed"] = inputs["seed"]
                            elif "noise_seed" in inputs:
                                metadata["seed"] = inputs["noise_seed"]
                        if "text" in inputs and isinstance(inputs["text"], str):
                            if "CLIPTextEncode" in class_type or metadata["prompt"] is None:
                                metadata["prompt"] = inputs["text"]
        except Exception as e:
            logger.debug(f"Could not extract metadata from {filename}: {e}")

        # Enrich from DB
        try:
            record = self.storage.get_execution_by_result_path(str(path))
            if record:
                metadata["persona"] = record.get("persona")
                ref_path = record.get("image_ref_path")
                if ref_path and Path(ref_path).exists():
                    metadata["ref_image"] = ref_path
        except Exception as e:
            logger.debug(f"Could not look up DB record for {filename}: {e}")

        return metadata

    def get_ref_image(self, filename: str, status: str = "pending") -> Optional[bytes]:
        path = self._dir_for_status(status) / filename
        try:
            record = self.storage.get_execution_by_result_path(str(path))
            if not record:
                return None
            ref_path = record.get("image_ref_path")
            if not ref_path or not Path(ref_path).exists():
                return None
            return Path(ref_path).read_bytes()
        except Exception as e:
            logger.debug(f"Could not get ref image for {filename}: {e}")
            return None

    # ------------------------------------------------------------------
    # Approve / disapprove / undo
    # ------------------------------------------------------------------

    def _move_image(self, filename: str, src_dir: Path, dest_dir: Path, new_name: Optional[str] = None) -> bool:
        src_path = src_dir / filename
        if not src_path.exists():
            logger.warning(f"Source not found: {src_path}")
            return False

        final_name = new_name if new_name else filename
        if not Path(final_name).suffix.lower() in IMAGE_EXTENSIONS:
            final_name += src_path.suffix

        dest_path = dest_dir / final_name
        if dest_path.exists():
            base, ext = os.path.splitext(final_name)
            dest_path = dest_dir / f"{base}_{int(time.time())}{ext}"

        shutil.move(str(src_path), str(dest_path))

        # Move companion .txt if exists
        txt_src = src_path.with_suffix(".txt")
        if txt_src.exists():
            shutil.move(str(txt_src), str(dest_path.with_suffix(".txt")))

        return True

    def approve_images(self, filenames: List[str], rename_map: Dict[str, str] = {}) -> dict:
        moved, failed = 0, []
        for fname in filenames:
            new_name = rename_map.get(fname) or None
            ok = self._move_image(fname, self.output_dir, self.approved_dir, new_name)
            if ok:
                moved += 1
            else:
                failed.append(fname)
        return {"moved": moved, "failed": failed}

    def disapprove_images(self, filenames: List[str]) -> dict:
        moved, failed = 0, []
        for fname in filenames:
            ok = self._move_image(fname, self.output_dir, self.disapproved_dir)
            if ok:
                moved += 1
            else:
                failed.append(fname)
        return {"moved": moved, "failed": failed}

    def undo_action(self, filenames: List[str], from_status: str) -> dict:
        src_dir = self._dir_for_status(from_status)
        moved, failed = 0, []
        for fname in filenames:
            ok = self._move_image(fname, src_dir, self.output_dir)
            if ok:
                moved += 1
            else:
                failed.append(fname)
        return {"moved": moved, "failed": failed}

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        stats: Dict[str, Dict[str, int]] = {}

        def _scan(directory: Path, approved: bool = False):
            for fname, mtime in self._scan_dir(directory):
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                if date_str not in stats:
                    stats[date_str] = {"pending": 0, "approved": 0, "disapproved": 0}
                if approved:
                    stats[date_str]["approved"] += 1
                elif directory == self.disapproved_dir:
                    stats[date_str]["disapproved"] += 1
                else:
                    stats[date_str]["pending"] += 1

        _scan(self.output_dir)
        _scan(self.approved_dir, approved=True)
        _scan(self.disapproved_dir)

        daily = [
            {
                "date": d,
                "pending": v["pending"],
                "approved": v["approved"],
                "disapproved": v["disapproved"],
                "total": sum(v.values()),
            }
            for d, v in sorted(stats.items(), reverse=True)
        ]

        totals = {
            "pending": sum(d["pending"] for d in daily),
            "approved": sum(d["approved"] for d in daily),
            "disapproved": sum(d["disapproved"] for d in daily),
            "total": sum(d["total"] for d in daily),
        }

        return {"daily": daily, "totals": totals}

    # ------------------------------------------------------------------
    # ZIP download
    # ------------------------------------------------------------------

    def build_zip(self, filenames: Optional[List[str]] = None, date: Optional[str] = None) -> bytes:
        """Build ZIP of approved images (by explicit list or by date)."""
        if date:
            all_files = self._scan_dir(self.approved_dir)
            filenames = [
                fname
                for fname, mtime in all_files
                if datetime.fromtimestamp(mtime).strftime("%Y-%m-%d") == date
            ]

        if not filenames:
            raise ValueError("No filenames specified for ZIP")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in filenames:
                # Try approved first, then pending
                for directory in (self.approved_dir, self.output_dir):
                    fpath = directory / fname
                    if fpath.exists():
                        zf.write(str(fpath), arcname=fname)
                        txt = fpath.with_suffix(".txt")
                        if txt.exists():
                            zf.write(str(txt), arcname=txt.name)
                        break

        return buf.getvalue()

    # ------------------------------------------------------------------
    # Execution record lookup
    # ------------------------------------------------------------------

    def lookup_execution(self, filename: str) -> Optional[dict]:
        all_completed = self.storage.get_all_completed_executions()
        for exc in all_completed:
            if exc.get("result_image_path") and os.path.basename(exc["result_image_path"]) == filename:
                return exc
        return None

    # ------------------------------------------------------------------
    # Daily notes
    # ------------------------------------------------------------------

    def load_notes(self) -> dict:
        if self.notes_file.exists():
            try:
                return json.loads(self.notes_file.read_text())
            except Exception:
                return {}
        return {}

    def save_note(self, date_str: str, text: str) -> bool:
        notes = self.load_notes()
        notes[date_str] = text
        try:
            self.notes_file.write_text(json.dumps(notes, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save note: {e}")
            return False
