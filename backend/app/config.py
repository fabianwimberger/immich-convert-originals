"""Environment configuration: process-level settings and first-boot seed values."""

import os
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


class Settings:
    """Process-level settings loaded from environment variables.

    Distinct from the app.models.settings.Settings DB row: this class covers
    infrastructure (paths, logging, CORS) that can't live in the database
    because it's needed before the database is reachable. Immich connection
    and default encoding values are DB-backed and editable from the UI;
    SEED_* below are only consulted once, to populate that DB row on first
    boot.
    """

    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "/app/data/app.db")
    TEMP_DIR: str = os.environ.get("TEMP_DIR", "/app/temp")
    FRONTEND_DIR: str = os.environ.get("FRONTEND_DIR", "/app/frontend")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    CORS_ORIGINS: list[str] = os.environ.get(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")

    @property
    def DATABASE_URL(self) -> str:
        return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"

    @classmethod
    def ensure_directories(cls) -> None:
        Path(cls.TEMP_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()


def seed_settings_from_env() -> dict[str, Any]:
    """Read first-boot default values for the DB-backed Settings row.

    Only consulted when no Settings row exists yet (see database.py
    lifespan startup) -- after that, the Settings page in the UI is
    authoritative and env vars are ignored.
    """
    return {
        "immich_api_base": os.environ.get("IMMICH_API_BASE", "").strip(),
        "immich_api_key": os.environ.get("IMMICH_API_KEY", "").strip(),
        "asset_types": os.environ.get("ASSET_TYPES", "IMAGE,VIDEO").strip(),
        "include_archived": _env_bool("INCLUDE_ARCHIVED", False),
        "include_deleted": _env_bool("INCLUDE_DELETED", False),
        "image_distance": _env_float("IMAGE_DISTANCE", 1.0),
        "image_distance_retry": _env_float("IMAGE_DISTANCE_RETRY", 2.0),
        "video_crf": _env_int("VIDEO_CRF", 36),
        "video_preset": _env_int("VIDEO_PRESET", 4),
        "video_max_dimension": _env_int("VIDEO_MAX_DIMENSION", 0),
        "video_audio_bitrate": os.environ.get("VIDEO_AUDIO_BITRATE", "64k").strip(),
        "video_crf_retry": _env_int("VIDEO_CRF_RETRY", 40),
        "enable_retry": _env_bool("ENABLE_RETRY", True),
        "accept_retry_output": _env_bool("ACCEPT_RETRY_OUTPUT", False),
        "allow_larger": _env_bool("ALLOW_LARGER", False),
        "concurrency": _env_int("CONCURRENCY", 2),
    }
