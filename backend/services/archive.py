"""
ArchiveService — Read-only gallery view of old server directories.

Archive directories are mounted read-only at:
  /app/archive/{server}/results/    ← generated result images
  /app/archive/{server}/processed/  ← reference/source images

Thumbnails are cached in a writable directory:
  /app/results/.archive_thumbnails/{server}/
"""
import io
import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PIL import Image

from backend.config import GlobalConfig

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ARCHIVE_BASE = Path("/app/archive")


class ArchiveService:
    def __init__(self):
        # Writable cache for generated thumbnails
        self.cache_dir = Path(GlobalConfig.OUTPUT_DIR) / ".archive_thumbnails"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Server discovery
    # ------------------------------------------------------------------

    def list_servers(self) -> List[str]:
        """Return sorted list of server names found under /app/archive/."""
        if not ARCHIVE_BASE.exists():
            return []
        return sorted(d.name for d in ARCHIVE_BASE.iterdir() if d.is_dir())

    def _results_dir(self, server: str) -> Path:
        return ARCHIVE_BASE / server / "results"

    def _processed_dir(self, server: str) -> Path:
        return ARCHIVE_BASE / server / "processed"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_dir(self, directory: Path) -> List[tuple]:
        """Return [(filename, mtime)] sorted newest first."""
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
        server: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        servers = [server] if server else self.list_servers()

        # Collect all result images across requested servers
        all_files: List[tuple] = []  # (server, filename, mtime)
        for srv in servers:
            for fname, mtime in self._scan_dir(self._results_dir(srv)):
                all_files.append((srv, fname, mtime))

        # Global newest-first sort
        all_files.sort(key=lambda x: x[2], reverse=True)

        total = len(all_files)
        pages = math.ceil(total / per_page) if total else 1
        page = max(1, min(page, pages))

        start = (page - 1) * per_page
        end = start + per_page
        page_slice = all_files[start:end]

        items = []
        for srv, filename, mtime in page_slice:
            dt = datetime.fromtimestamp(mtime)
            items.append(
                {
                    "server": srv,
                    "filename": filename,
                    "thumbnail_url": (
                        f"/api/archive/thumbnail"
                        f"?server={srv}&filename={filename}"
                    ),
                    "created_at": mtime,
                    "date": dt.strftime("%Y-%m-%d"),
                }
            )

        return {
            "servers": self.list_servers(),
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
        }

    # ------------------------------------------------------------------
    # Thumbnail generation (cached)
    # ------------------------------------------------------------------

    def get_thumbnail(self, server: str, filename: str) -> Optional[bytes]:
        original_path = self._results_dir(server) / filename
        if not original_path.exists():
            return None

        server_cache = self.cache_dir / server
        server_cache.mkdir(parents=True, exist_ok=True)
        thumb_path = server_cache / f"thumb_{filename}"

        # Serve from cache if fresh
        try:
            if (
                thumb_path.exists()
                and thumb_path.stat().st_mtime >= original_path.stat().st_mtime
            ):
                return thumb_path.read_bytes()
        except OSError:
            pass

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
            logger.error(
                f"Archive thumbnail failed for {server}/{filename}: {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Metadata extraction from PNG ComfyUI embed
    # ------------------------------------------------------------------

    def extract_metadata(self, server: str, filename: str) -> dict:
        path = self._results_dir(server) / filename
        metadata = {
            "seed": None,
            "prompt": None,
            "persona": None,
            "ref_image": None,
            "raw_metadata": {},
        }

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
                            if (
                                "CLIPTextEncode" in class_type
                                or metadata["prompt"] is None
                            ):
                                metadata["prompt"] = inputs["text"]
        except Exception as e:
            logger.debug(
                f"Could not extract metadata from archive {server}/{filename}: {e}"
            )

        return metadata

    # ------------------------------------------------------------------
    # Reference image lookup (from processed/)
    # ------------------------------------------------------------------

    def get_ref_image(self, server: str, filename: str) -> Optional[bytes]:
        """
        Return bytes for the reference/processed image paired with a result.

        Strategy:
        1. Parse the result image's ComfyUI PNG metadata.
        2. Find any LoadImage node — its 'image' input is the reference filename.
        3. Resolve that filename in the server's processed/ directory.
        4. If the stored value is an absolute path, fall back to its basename.
        """
        result_path = self._results_dir(server) / filename
        processed_dir = self._processed_dir(server)

        try:
            with Image.open(result_path) as img:
                meta = img.info
                if "prompt" not in meta:
                    return None
                prompt_data = json.loads(meta["prompt"])
                for node_id, node_data in prompt_data.items():
                    class_type = node_data.get("class_type", "")
                    inputs = node_data.get("inputs", {})
                    if "LoadImage" not in class_type:
                        continue
                    ref_input = inputs.get("image", "")
                    if not ref_input:
                        continue
                    # Try as a bare filename
                    ref_filename = Path(ref_input).name
                    for candidate in (
                        processed_dir / ref_filename,
                        processed_dir / ref_input,  # in case it's relative
                    ):
                        if candidate.exists():
                            return candidate.read_bytes()
        except Exception as e:
            logger.debug(
                f"Could not get ref image for archive {server}/{filename}: {e}"
            )

        return None

    # ------------------------------------------------------------------
    # Full image download (read-only, no copy)
    # ------------------------------------------------------------------

    def get_image(self, server: str, filename: str) -> Optional[bytes]:
        path = self._results_dir(server) / filename
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None
