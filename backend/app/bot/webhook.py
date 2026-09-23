"""Webhook бота MAX. Разделы 40, 41, 51, 75 тех-доки.

Webhook и REST API живут в одном приложении (раздел 75), но обычной
авторизацией Mini App webhook не защищён: его подлинность подтверждает
заголовок `X-Max-Bot-Api-Secret` с отдельным секретом `MAX_WEBHOOK_SECRET`
(раздел 41). Проверку заголовка выполняет сама `maxapi`: при неверном или
отсутствующем секрете возвращается `403`.

`MAX_BOT_TOKEN` и `MAX_WEBHOOK_SECRET` — разные секреты; путать их нельзя.
"""

import logging
from typing import TYPE_CHECKING

from app.bot.dispatcher import get_bot, get_dispatcher
from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from maxapi.webhook.fastapi import FastAPIMaxWebhook

logger = logging.getLogger("app.bot")


def setup_bot_webhook(app: "FastAPI") -> "FastAPIMaxWebhook | None":
    """Подключает маршрут webhook'а, если бот настроен.

    Без токена или секрета маршрут не заводится вовсе: принимать обновления
    некому, а открытый эндпоинт без проверки секрета заводить нельзя.
    """
    bot = get_bot()
    if bot is None:
        logger.warning("Бот MAX не настроен: webhook не подключён")
        return None
    if not settings.max_webhook_secret:
        logger.error(
            "MAX_WEBHOOK_SECRET не задан: webhook не подключён, "
            "принимать обновления без проверки секрета нельзя"
        )
        return None

    from maxapi.webhook.fastapi import FastAPIMaxWebhook

    webhook = FastAPIMaxWebhook(
        dp=get_dispatcher(), bot=bot, secret=settings.max_webhook_secret
    )
    webhook.setup(app, path=settings.max_webhook_path)
    logger.info("Webhook MAX подключён на %s", settings.max_webhook_path)
    return webhook


def webhook_url() -> str:
    """Адрес, который регистрируется в MAX (раздел 51)."""
    if settings.max_webhook_url:
        return settings.max_webhook_url
    return f"{settings.app_url.rstrip('/')}{settings.max_webhook_path}"


async def subscribe_webhook() -> None:
    """Регистрирует webhook в MAX при запуске production (раздел 51).

    Webhook работает только по HTTPS (раздел 41), поэтому адрес без `https://`
    не регистрируется. Ошибка регистрации не должна мешать приложению
    подняться: REST API работает независимо от бота.
    """
    bot = get_bot()
    if bot is None:
        return

    url = webhook_url()
    if not url.startswith("https://"):
        logger.error("Webhook MAX не зарегистрирован: адрес %s не HTTPS", url)
        return

    try:
        await bot.subscribe_webhook(url=url, secret=settings.max_webhook_secret)
    except Exception:  # noqa: BLE001 — бот не должен мешать старту API
        logger.exception("Не удалось зарегистрировать webhook MAX")
        return
    logger.info("Webhook MAX зарегистрирован")
