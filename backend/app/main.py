"""Точка входа backend.

REST API живёт под /api/*, webhook бота будет подключён на /webhook/max,
healthcheck — на /health без авторизации (разделы 75, 76 тех-доки).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from tortoise.contrib.fastapi import RegisterTortoise

from app.auth.router import router as auth_router
from app.candidates.router import router as candidate_router
from app.core.config import settings
from app.core.database import TORTOISE_ORM
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, setup_logging
from app.matching.router import router as feed_router
from app.users.router import router as users_router

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.avatars_dir.mkdir(parents=True, exist_ok=True)
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)

    # RegisterTortoise, а не голый Tortoise.init: lifespan выполняется в
    # отдельной задаче, и подключение должно быть доступно задачам запросов.
    async with RegisterTortoise(application, config=TORTOISE_ORM):
        logger.info("Приложение запущено, окружение=%s", settings.app_env)
        yield
    logger.info("Приложение остановлено")


app = FastAPI(
    title="MAX Найм API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(candidate_router)
# Раньше любого /vacancies/{id}, иначе feed уедет в параметр пути
api_router.include_router(feed_router)
app.include_router(api_router)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Healthcheck не требует пользовательской сессии."""
    return {"status": "ok"}
