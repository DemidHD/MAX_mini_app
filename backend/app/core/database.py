"""Подключение к PostgreSQL через Tortoise ORM.

`TORTOISE_ORM` используется и приложением, и aerich (см. [tool.aerich] в pyproject.toml).
"""

from datetime import datetime, timezone

from tortoise import Tortoise

from app.core.config import settings

MODELS_MODULES = [
    "app.users.models",
    "app.auth.models",
    "app.candidates.models",
    "app.vacancies.models",
    "app.applications.models",
    "app.interviews.models",
    "app.analytics.models",
    "app.notifications.models",
    "app.skills.models",
    "aerich.models",
]

TORTOISE_ORM: dict = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": MODELS_MODULES,
            "default_connection": "default",
        },
    },
    # Tortoise на PostgreSQL создаёт для DatetimeField колонки TIMESTAMPTZ
    # (в тех-доке они описаны как TIMESTAMP). Работаем с осознанным временем
    # в UTC, чтобы не смешивать naive и aware datetime.
    "use_tz": True,
    "timezone": "UTC",
}


def utcnow() -> datetime:
    """Текущее время в UTC с tzinfo — под TIMESTAMPTZ-колонки."""
    return datetime.now(timezone.utc)


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_ORM)


async def close_db() -> None:
    await Tortoise.close_connections()
