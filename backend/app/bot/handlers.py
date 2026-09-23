"""Обработчики бота. Раздел 43 тех-доки.

Минимум для P0: `/start` и `bot_started`. Оба делают одно — дают человеку
ссылку, по которой открывается Mini App. Бот в P0 нужен прежде всего как
канал уведомлений (раздел 46), а не как самостоятельный интерфейс.
"""

import logging
from typing import TYPE_CHECKING, Any

from app.notifications import messages

if TYPE_CHECKING:
    from maxapi.dispatcher import Router

logger = logging.getLogger("app.bot")


def build_router() -> "Router":
    """Роутер с обработчиками команд и событий бота."""
    from maxapi.dispatcher import Router
    from maxapi.filters.command import Command

    router = Router()
    router.bot_started()(handle_bot_started)
    router.message_created(Command("start"))(handle_start_command)
    return router


async def handle_bot_started(event: Any) -> None:
    """Пользователь открыл диалог с ботом."""
    user = getattr(event, "user", None)
    user_id = getattr(user, "user_id", None)
    await _greet(event, user_id)


async def handle_start_command(event: Any) -> None:
    """Команда `/start` в диалоге с ботом."""
    _, user_id = event.get_ids()
    await _greet(event, user_id)


async def _greet(event: Any, user_id: int | None) -> None:
    """Отправляет приветствие со ссылкой на Mini App.

    Ошибка отправки не должна ронять обработку обновления: MAX повторит
    доставку события, а падение обработчика ничего не исправит.
    """
    if user_id is None:
        logger.warning("Событие бота без идентификатора пользователя")
        return

    bot = getattr(event, "bot", None)
    if bot is None:
        logger.error("Событие бота пришло без экземпляра бота")
        return

    try:
        await bot.send_message(user_id=user_id, text=messages.bot_greeting())
    except Exception:  # noqa: BLE001 — обработчик не должен падать
        logger.exception("Не удалось ответить пользователю %s", user_id)
