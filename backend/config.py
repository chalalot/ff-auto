import os
from dotenv import load_dotenv

load_dotenv()


class GlobalConfig:
    """Global configurations."""
    # Database access goes through backend.database.engine / db_utils
    # (DATABASE_URL is the single source of truth) — no DB settings here.

    # OPENAI
    OPENAI_API_BASE = os.getenv("OPENAI_BASE_URL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # GEMINI (Google)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # LLM media evaluator (OpenAI-compatible endpoint)
    EVALUATOR_MODEL = os.getenv("EVALUATOR_MODEL", "gemma-4-31b-it")
    _EVALUATOR_IS_GOOGLE_MODEL = EVALUATOR_MODEL.startswith(("gemini-", "gemma-", "models/gemini-", "models/gemma-", "google/gemini-", "google/gemma-"))
    _DEFAULT_EVALUATOR_API_BASE = (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
        if _EVALUATOR_IS_GOOGLE_MODEL and GEMINI_API_KEY
        else OPENAI_API_BASE
    )
    EVALUATOR_API_BASE = os.getenv("EVALUATOR_BASE_URL", os.getenv("EVALUATOR_API_BASE", _DEFAULT_EVALUATOR_API_BASE))
    EVALUATOR_API_KEY = os.getenv(
        "EVALUATOR_API_KEY",
        GEMINI_API_KEY if _EVALUATOR_IS_GOOGLE_MODEL and EVALUATOR_API_BASE else OPENAI_API_KEY,
    )

    # GROK (xAI)
    GROK_API_KEY = os.getenv("GROK_API_KEY")

    # API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")

    DEBUG = False

    # RunwayML
    RUNWAY_API_KEY = os.getenv("RUNWAYML_API_SECRET", None)

    # Kling AI
    KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY")
    KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY")

    # Google Drive
    GDRIVE_CREDENTIALS_PATH = os.getenv("GDRIVE_CREDENTIALS_PATH", "ff-auto-drive.json")
    # Accept either a raw folder ID or a full Drive URL
    _gdrive_upload_raw = os.getenv("GDRIVE_UPLOAD_FOLDER_ID", "")
    import re as _re
    _gdrive_match = _re.search(r"/folders/([a-zA-Z0-9_-]+)", _gdrive_upload_raw)
    GDRIVE_UPLOAD_FOLDER_ID = _gdrive_match.group(1) if _gdrive_match else _gdrive_upload_raw

    # RunPod
    RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
    RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")

    # Hugging Face
    HF_TOKEN = os.getenv("HF_TOKEN", "")

    # Google Cloud Storage
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "soulie-gcp-bucket")
    GCS_CREDENTIALS_PATH = os.getenv("GCS_CREDENTIALS_PATH", "soulie-gcp-bucket.json")
    GCS_PUBLIC_BASE_URL = os.getenv("GCS_PUBLIC_BASE_URL", "https://storage.googleapis.com/soulie-gcp-bucket")
    GCS_CREDENTIALS_JSON = os.getenv("GCS_CREDENTIALS")

    # ComfyUI API Settings
    CLOUD_COMFY_API_URL = os.getenv("CLOUD_COMFY_API_URL", os.getenv("COMFYUI_API_URL", "https://cloud.comfy.org/api"))
    COMFYUI_API_KEY = os.getenv("COMFYUI_API_KEY")
    COMFYUI_API_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", "1000"))
    COMFYUI_POLL_INTERVAL = int(os.getenv("COMFYUI_POLL_INTERVAL", "5"))
    COMFYUI_MAX_POLL_TIME = int(os.getenv("COMFYUI_MAX_POLL_TIME", "3600"))
    COMFYUI_MAX_RETRIES = int(os.getenv("COMFYUI_MAX_RETRIES", "3"))

    # Storage Directories (Mounted Volumes)
    INPUT_DIR = os.getenv("INPUT_DIR", "Sorted")
    PROCESSED_DIR = os.getenv("PROCESSED_DIR", "processed")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "results")
    VIDEO_DIR = os.getenv("VIDEO_DIR", "raw_video")

    # Prompts directory (for personas, presets, templates)
    PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
    UPLOAD_GCS = False

    # Root that local media paths submitted to the evaluator must stay within.
    # Prevents path traversal / arbitrary file reads of files outside the
    # generated-media tree. Remote (http/https/data) URLs are unaffected.
    EVALUATION_MEDIA_ROOT = os.getenv("EVALUATION_MEDIA_ROOT", os.getcwd())

    @classmethod
    def get_sqlite_connect_args(cls):
        if cls.DB_TYPE == "sqlite":
            return {
                "check_same_thread": False,
                "timeout": cls.SQLITE_TIMEOUT,
            }
        return {}
