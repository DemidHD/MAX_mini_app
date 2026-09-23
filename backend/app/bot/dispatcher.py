"""Бот MAX: экземпляр и диспетчер. Разделы 38-43 тех-доки.

Бот и Mini App живут в одном backend (раздел 42), поэтому бот создаётся здесь
и переиспользуется и webhook'ом, и сервисом уведомлений.

Объекты создаются лениво: без `MAX_BOT_TOKEN` (локальная разработка, тесты)
бота нет вовсе, а P0-маршрут по разделу 83 обязан работать и без него —
теряются только сообщения в MAX.
"""

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from maxapi import Bot, Dispatcher

logger = logging.getLogger("app.bot")

_bot: "Bot | None" = None
_dispatcher: "Dispatcher | None" = None


def bot_configured() -> bool:
    """Есть ли всё, что нужно для работы бота."""
    return bool(settings.bot_enabled and settings.max_bot_token)


def get_bot() -> "Bot | None":
    """Экземпляр бота или `None`, если бот не настроен."""
    global _bot

    if not bot_configured():
        return None
    if _bot is None:
        from maxapi import Bot

        _bot = Bot(token=settings.max_bot_token)
        logger.info("Бот MAX инициализирован")
    return _bot


def get_dispatcher() -> "Dispatcher":
    """Диспетчер с подключёнными обработчиками (раздел 43)."""
    global _dispatcher

    if _dispatcher is None:
        from maxapi import Dispatcher

        from app.bot.handlers import build_router

        _dispatcher = Dispatcher()
        _dispatcher.include_routers(build_router())
    return _dispatcher


async def close_bot() -> None:
    """Закрывает HTTP-сессию бота при остановке приложения (раздел 51)."""
    global _bot

    if _bot is None:
        return
    try:
        await _bot.close_session()
    except Exception:  # noqa: BLE001 — остановку это прерывать не должно
        logger.warning("Не удалось закрыть сессию бота", exc_info=True)
    finally:
        _bot = None
        logger.info("Ресурсы бота MAX освобождены")


def reset() -> None:
    """Сбрасывает созданные объекты. Нужен тестам и смене конфигурации."""
    global _bot, _dispatcher

    _bot = None
    _dispatcher = None
