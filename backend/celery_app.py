import os
from celery import Celery
from kombu import Queue
from dotenv import load_dotenv

load_dotenv()

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
    },
)


if __name__ == "__main__":
    celery_app.start()
