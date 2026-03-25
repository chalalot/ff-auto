import os
import threading
from dotenv import load_dotenv

load_dotenv()


class GlobalConfig:
    """Global configurations."""
    # DATABASE TYPE
    DB_TYPE = os.getenv("DB_TYPE", "sqlite")  # sqlite or postgres

    # PostgreSQL specific (if DB_TYPE is postgres)
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "mkt_agent")

    # DATABASE URLs - constructed based on DB_TYPE
    if DB_TYPE == "postgres":
        DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        ASYNC_DB_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    else:
        DB_URL = os.getenv("DB_URL", "sqlite:///./image_logs.db")
        ASYNC_DB_URL = DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

    IS_ECHO_QUERY = bool(os.getenv("IS_ECHO_QUERY", False))

    # SQLite specific settings
    SQLITE_TIMEOUT = int(os.getenv("SQLITE_TIMEOUT", "30"))
    SQLITE_BUSY_TIMEOUT = int(os.getenv("SQLITE_BUSY_TIMEOUT", "120000"))

    DB_CONNECTION_LOCAL = threading.local()

    # OPENAI
    OPENAI_API_BASE = os.getenv("OPENAI_BASE_URL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # GROK (xAI)
    GROK_API_KEY = os.getenv("GROK_API_KEY")

    # GEMINI (Google)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

    # Google Cloud Storage
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "soulie-gcp-bucket")
    GCS_CREDENTIALS_PATH = os.getenv("GCS_CREDENTIALS_PATH", "soulie-gcp-bucket.json")
    GCS_PUBLIC_BASE_URL = os.getenv("GCS_PUBLIC_BASE_URL", "https://storage.googleapis.com/soulie-gcp-bucket")
    GCS_CREDENTIALS_JSON = os.getenv("GCS_CREDENTIALS")

    # ComfyUI API Settings
    CLOUD_COMFY_API_URL = os.getenv("COMFYUI_API_URL", os.getenv("CLOUD_COMFY_API_URL", "https://cloud.comfy.org/api"))
    COMFYUI_API_KEY = os.getenv("COMFYUI_API_KEY")
    COMFYUI_API_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", "1000"))
    COMFYUI_POLL_INTERVAL = int(os.getenv("COMFYUI_POLL_INTERVAL", "5"))
    COMFYUI_MAX_POLL_TIME = int(os.getenv("COMFYUI_MAX_POLL_TIME", "3600"))
    COMFYUI_MAX_RETRIES = int(os.getenv("COMFYUI_MAX_RETRIES", "3"))

    # Storage Directories (Mounted Volumes)
    INPUT_DIR = os.getenv("INPUT_DIR", "Sorted")
    PROCESSED_DIR = os.getenv("PROCESSED_DIR", "processed")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "results")

    # Prompts directory (for personas, presets, templates)
    PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")

    @classmethod
    def get_sqlite_connect_args(cls):
        if cls.DB_TYPE == "sqlite":
            return {
                "check_same_thread": False,
                "timeout": cls.SQLITE_TIMEOUT,
            }
        return {}
