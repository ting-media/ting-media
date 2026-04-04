import os
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)

_env_path = BASE_DIR / ".env"
load_dotenv(_env_path)


class Config:
    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    @classmethod
    def set(cls, key: str, value: str):
        """Persist a key-value pair to .env and update current process env."""
        _env_path.touch(exist_ok=True)
        set_key(str(_env_path), key, str(value))
        os.environ[key] = str(value)

    # ── Accessors ────────────────────────────────────────────────────────────

    @classmethod
    def anthropic_api_key(cls) -> str:
        return cls.get("ANTHROPIC_API_KEY")

    @classmethod
    def gemini_api_key(cls) -> str:
        return cls.get("GEMINI_API_KEY")

    @classmethod
    def google_service_account_path(cls) -> str:
        return cls.get("GOOGLE_SERVICE_ACCOUNT_KEY_PATH")

    @classmethod
    def google_drive_root_folder_id(cls) -> str:
        return cls.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")

    @classmethod
    def scan_url(cls) -> str:
        return cls.get("SCAN_URL", "https://www.auto.co.il/articles/car-news/")

    @classmethod
    def scan_times(cls) -> list[str]:
        raw = cls.get("SCAN_TIMES", "07:00")
        return [t.strip() for t in raw.split(",") if t.strip()]

    @classmethod
    def output_dir(cls) -> Path:
        return Path(cls.get("OUTPUT_DIR", str(BASE_DIR / "output")))

    # ── State file paths ──────────────────────────────────────────────────────

    PROCESSED_FILE = STATE_DIR / "processed_articles.json"
    JOBS_FILE = STATE_DIR / "jobs.json"
