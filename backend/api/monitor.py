import os
import subprocess
from pathlib import Path

import psutil
from fastapi import APIRouter

from backend.config import GlobalConfig
from backend.database.image_logs_storage import ImageLogsStorage

router = APIRouter()


@router.get("/health")
def health():
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": cpu,
        "ram": {
            "total_gb": round(ram.total / 1e9, 2),
            "used_gb": round(ram.used / 1e9, 2),
            "percent": ram.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1e9, 2),
            "used_gb": round(disk.used / 1e9, 2),
            "percent": disk.percent,
        },
    }


@router.get("/processes")
def list_processes():
    results = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline"]):
        try:
            info = proc.info
            cmdline = " ".join(info.get("cmdline") or [])
            if "python" in info.get("name", "").lower() or "celery" in cmdline:
                results.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu_percent": info["cpu_percent"],
                        "memory_percent": round(info["memory_percent"] or 0, 2),
                        "cmdline": cmdline[:120],
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results


@router.get("/db-stats")
def db_stats():
    storage = ImageLogsStorage()
    recent = storage.get_recent_executions(limit=10000)
    counts = {"total": len(recent), "pending": 0, "completed": 0, "failed": 0}
    for row in recent:
        status = row.get("status", "pending")
        if status in counts:
            counts[status] += 1
    return {"images": counts}


@router.get("/filesystem")
def filesystem():
    def _count(directory: str) -> int:
        p = Path(directory)
        if not p.exists():
            return 0
        exts = {".png", ".jpg", ".jpeg", ".webp"}
        return sum(1 for f in p.iterdir() if f.is_file() and f.suffix.lower() in exts)

    return {
        "input": _count(GlobalConfig.INPUT_DIR),
        "processed": _count(GlobalConfig.PROCESSED_DIR),
        "output_pending": _count(GlobalConfig.OUTPUT_DIR),
        "output_approved": _count(os.path.join(GlobalConfig.OUTPUT_DIR, "approved")),
        "output_disapproved": _count(os.path.join(GlobalConfig.OUTPUT_DIR, "disapproved")),
    }
