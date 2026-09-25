"""Точка входа backend.

REST API живёт под /api/*, webhook бота — на /webhook/max, healthcheck —
на /health без авторизации (разделы 75, 76 тех-доки).
"""

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from tortoise.contrib.fastapi import RegisterTortoise

from app.ai.router import router as ai_router
from app.ai.service import configure_ai_service
from app.analytics.router import router as analytics_router
from app.applications.router import employer_router, vacancies_router
from app.applications.router import router as applications_router
from app.auth.router import router as auth_router
from app.bot.dispatcher import close_bot
from app.bot.webhook import setup_bot_webhook, subscribe_webhook
from app.candidates.router import router as candidate_router
from app.core.config import settings
from app.core.database import TORTOISE_ORM
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, setup_logging
from app.interviews.router import router as matches_router
from app.interviews.router import vacancies_router as slots_router
from app.matching.router import router as feed_router
from app.users.router import router as users_router
from app.vacancies.router import employer_router as employer_vacancies_router
from app.vacancies.router import router as vacancies_crud_router

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    configure_ai_service()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.avatars_dir.mkdir(parents=True, exist_ok=True)
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncExitStack() as stack:
        # RegisterTortoise, а не голый Tortoise.init: lifespan выполняется в
        # отдельной задаче, и подключение должно быть доступно задачам запросов.
        await stack.enter_async_context(
            RegisterTortoise(application, config=TORTOISE_ORM)
        )

        if bot_webhook is not None:
            # Раздел 51: диспетчер поднимается вместе с приложением.
            # Недоступный MAX не должен мешать REST API подняться (раздел 83):
            # без бота теряются только уведомления.
            try:
                await stack.enter_async_context(bot_webhook.lifespan(application))
            except Exception:  # noqa: BLE001 — бот не критичен для API
                logger.exception(
                    "Бот MAX не запустился: API работает без уведомлений"
                )
            else:
                if settings.is_production:
                    # В разработке адрес недоступен из интернета, регистрировать
                    # его в MAX нечем и незачем
                    await subscribe_webhook()

        logger.info("Приложение запущено, окружение=%s", settings.app_env)
        try:
            yield
        finally:
            # Раздел 51: ресурсы maxapi освобождаются при остановке
            await close_bot()
    logger.info("Приложение остановлено")


app = FastAPI(
    title="MAX Найм API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

# Webhook бота подключается до старта: маршруты регистрируются на импорте.
# Без токена или секрета останется `None`, и приложение работает без бота.
bot_webhook = setup_bot_webhook(app)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(candidate_router)
# Раньше любого /vacancies/{id}, иначе feed уедет в параметр пути
api_router.include_router(feed_router)
api_router.include_router(vacancies_crud_router)
api_router.include_router(vacancies_router)
api_router.include_router(slots_router)
api_router.include_router(applications_router)
api_router.include_router(employer_router)
api_router.include_router(employer_vacancies_router)
api_router.include_router(matches_router)
api_router.include_router(ai_router)
api_router.include_router(analytics_router)
app.include_router(api_router)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Healthcheck не требует пользовательской сессии."""
    return {"status": "ok"}
