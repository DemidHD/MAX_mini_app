"""Точка входа backend.

REST API живёт под /api/*, webhook бота будет подключён на /webhook/max,
healthcheck — на /health без авторизации (разделы 75, 76 тех-доки).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from tortoise import Tortoise

from app.core.config import settings
from app.core.database import TORTOISE_ORM
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, setup_logging

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.avatars_dir.mkdir(parents=True, exist_ok=True)
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)

    await Tortoise.init(config=TORTOISE_ORM)
    logger.info("Приложение запущено, окружение=%s", settings.app_env)
    try:
        yield
    finally:
        await Tortoise.close_connections()
        logger.info("Приложение остановлено")


app = FastAPI(
    title="MAX Найм API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

api_router = APIRouter(prefix="/api")
app.include_router(api_router)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Healthcheck не требует пользовательской сессии."""
    return {"status": "ok"}
