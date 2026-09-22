"""Конфигурация приложения. Единственный источник значений — environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env лежит в корне репозитория и читается по абсолютному пути: иначе значения
# подхватывались бы только при запуске из корня, а из backend/ (pytest, uvicorn)
# молча брались бы значения по умолчанию. В Docker файла нет — там env vars.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Более поздний файл переопределяет более ранний
        env_file=(_REPO_ROOT / ".env", _BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    app_env: str = "development"
    app_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # --- База данных ---
    database_url: str = "postgres://max_hiring:change_me@postgres:5432/max_hiring"
    # DSN для pytest. database_url указывает на хост `postgres` из сети Docker,
    # с машины разработчика это имя не резолвится — тесты ходят на localhost.
    test_database_url: str = ""

    # --- MAX ---
    # Проверка подписи initData и Bot API. Секрет живёт только на backend.
    max_bot_token: str = ""
    # Секрет webhook'а — отдельный от токена бота (раздел 41 тех-доки).
    max_webhook_secret: str = ""

    # --- Сессии ---
    session_secret: str = ""
    session_ttl_hours: int = 720
    session_cookie_name: str = "max_hiring_session"
    auth_date_max_age_seconds: int = 86400
    auth_rate_limit_requests: int = 120
    auth_rate_limit_window_seconds: int = 60
    session_cleanup_interval_seconds: int = 300

    # --- Локальное файловое хранилище ---
    storage_root: Path = Path("/app/storage")
    avatar_max_size_bytes: int = 5 * 1024 * 1024
    # NoDecode: значение приходит списком через запятую, а не JSON
    avatar_allowed_mime_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]

    # --- AI (P1) ---
    ai_api_url: str = ""
    ai_api_key: str = ""

    @field_validator("avatar_allowed_mime_types", mode="before")
    @classmethod
    def _split_mime_types(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def avatars_dir(self) -> Path:
        return self.storage_root / "avatars"

    @property
    def resumes_dir(self) -> Path:
        return self.storage_root / "resumes"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
