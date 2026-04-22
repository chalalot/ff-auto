"""Dependency injection: shared service singletons."""
from functools import lru_cache

from backend.database.image_logs_storage import ImageLogsStorage
from backend.services.image_processing import ImageProcessingService
from backend.services.gallery import GalleryService
from backend.services.config import ConfigService


@lru_cache
def get_image_logs_storage() -> ImageLogsStorage:
    return ImageLogsStorage()


@lru_cache
def get_image_processing_service() -> ImageProcessingService:
    return ImageProcessingService()


@lru_cache
def get_gallery_service() -> GalleryService:
    return GalleryService()


@lru_cache
def get_config_service() -> ConfigService:
    return ConfigService()


from backend.services.video import VideoService


@lru_cache
def get_video_service() -> VideoService:
    return VideoService()


from backend.services.archive import ArchiveService


@lru_cache
def get_archive_service() -> ArchiveService:
    return ArchiveService()


from backend.database.runpod_jobs_storage import RunpodJobsStorage


@lru_cache
def get_runpod_jobs_storage() -> RunpodJobsStorage:
    return RunpodJobsStorage()
