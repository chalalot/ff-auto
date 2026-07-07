import os
from celery import Celery
from celery.signals import worker_init
from kombu import Queue
from dotenv import load_dotenv

load_dotenv()


def check_database_ready_on_worker_init(**kwargs):
    """Fail fast if the DB is unreachable or not migrated to alembic head."""
    from backend.database.engine import assert_database_ready

    assert_database_ready()


worker_init.connect(check_database_ready_on_worker_init, weak=False)

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    "variations_mood",
    broker=broker_url,
    backend=result_backend,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_queues=(
        Queue("image"),
        Queue("video"),
    ),
    task_default_queue="image",
    task_routes={
        "backend.tasks.process_image_task": {"queue": "image"},
        "backend.tasks.download_execution_task": {"queue": "image"},
        "backend.tasks.merge_videos_task": {"queue": "video"},
        "backend.tasks.analyze_music_task": {"queue": "video"},
        "backend.tasks.poll_comfy_video_task": {"queue": "video"},
        "backend.tasks.generate_storyboard_task": {"queue": "video"},
        "backend.tasks.poll_kling_video_task": {"queue": "video"},
        "backend.tasks.caption_export_task": {"queue": "image"},
    },
)


if __name__ == "__main__":
    celery_app.start()
