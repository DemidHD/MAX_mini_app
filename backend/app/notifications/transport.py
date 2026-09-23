"""Канал доставки уведомлений. Разделы 44, 45 тех-доки.

Бизнес-код не знает ни про `maxapi`, ни про то, включён ли бот: он вызывает
`NotificationService`, а тот — транспорт. Благодаря этому уведомления можно
выключить (`BOT_ENABLED=false`) или подменить в тестах, не трогая сценарий.
"""

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger("app.notifications")


class NotificationsDisabledError(RuntimeError):
    """Канал уведомлений выключен или не настроен.

    Отличается от ошибки отправки: сообщение не отправлено и не будет
    отправлено до изменения конфигурации, повторять попытку бессмысленно.
    """


@runtime_checkable
class NotificationTransport(Protocol):
    """Минимум, который нужен сервису уведомлений."""

    async def send(self, user_id: int, text: str) -> None:
        """Отправляет сообщение пользователю MAX.

        Бросает исключение, если отправка не удалась: решение о повторе
        принимает `NotificationService`.
        """


class MaxBotTransport:
    """Отправка через MAX Bot API (`maxapi`).

    Раздел 45: персональное уведомление отправляется по `user_id`.
    """

    async def send(self, user_id: int, text: str) -> None:
        # Импорт внутри метода: без настроенного бота модуль `maxapi` не нужен
        from app.bot.dispatcher import get_bot

        bot = get_bot()
        if bot is None:
            raise NotificationsDisabledError("Бот MAX не настроен")
        await bot.send_message(user_id=user_id, text=text)


class DisabledTransport:
    """Заглушка для окружения без бота: сообщение никуда не уходит."""

    async def send(self, user_id: int, text: str) -> None:
        logger.info("Уведомления выключены, сообщение не отправлено")
        raise NotificationsDisabledError("Уведомления выключены настройкой")


def build_transport() -> NotificationTransport:
    """Транспорт по текущей конфигурации."""
    from app.core.config import settings

    if not settings.bot_enabled or not settings.max_bot_token:
        logger.warning(
            "Канал уведомлений не настроен: сообщения в MAX отправляться не будут"
        )
        return DisabledTransport()
    return MaxBotTransport()
