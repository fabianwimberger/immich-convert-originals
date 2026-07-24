"""Environment configuration: process-level infrastructure settings."""

import os
from pathlib import Path


class Settings:
    """Process-level settings loaded from environment variables.

    Distinct from the app.models.settings.Settings DB row: this class covers
    infrastructure (paths, logging, CORS) that can't live in the database
    because it's needed before the database is reachable. Immich connection
    and default encoding/output values are DB-backed and editable entirely
    from the Settings page -- there is no env-var seeding for them.
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
