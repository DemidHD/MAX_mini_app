"""Бот MAX: webhook, секрет и обработчики. Разделы 40, 41, 43, 51 тех-доки."""

from typing import Any, AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.bot import dispatcher as bot_dispatcher
from app.bot import webhook as bot_webhook
from app.bot.handlers import handle_bot_started, handle_start_command
from app.core.config import settings
from app.notifications import messages

WEBHOOK_SECRET = "webhook-secret-for-tests"


@pytest_asyncio.fixture
async def configured_bot(monkeypatch) -> AsyncIterator[None]:
    """Окружение с настроенным ботом.

    Сам `maxapi.Bot` только создаётся: сетевых вызовов в тестах нет, так как
    диспетчер не запускается, а обработчики проверяются отдельно.
    """
    monkeypatch.setattr(settings, "bot_enabled", True)
    monkeypatch.setattr(settings, "max_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "max_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "max_webhook_path", "/webhook/max")
    bot_dispatcher.reset()
    yield
    bot_dispatcher.reset()


def _app_with_webhook() -> tuple[FastAPI, Any]:
    app = FastAPI()
    webhook = bot_webhook.setup_bot_webhook(app)
    return app, webhook


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class _FakeBot:
    """Бот, который запоминает вызовы вместо обращения к MAX Bot API."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.subscriptions: list[tuple[str, str | None]] = []
        self.fail = False

    async def send_message(self, *, user_id: int, text: str) -> None:
        if self.fail:
            raise RuntimeError("MAX недоступен")
        self.messages.append((user_id, text))

    async def subscribe_webhook(
        self, *, url: str, secret: str | None = None
    ) -> None:
        self.subscriptions.append((url, secret))


# --- Подключение webhook ----------------------------------------------------


async def test_webhook_is_not_registered_without_bot(monkeypatch) -> None:
    """Без токена принимать обновления некому."""
    monkeypatch.setattr(settings, "max_bot_token", "")
    bot_dispatcher.reset()

    app, webhook = _app_with_webhook()

    assert webhook is None
    assert not [route for route in app.routes if "/webhook" in getattr(route, "path", "")]


async def test_webhook_is_not_registered_without_secret(monkeypatch) -> None:
    """Раздел 41: открытый webhook без проверки секрета заводить нельзя."""
    monkeypatch.setattr(settings, "bot_enabled", True)
    monkeypatch.setattr(settings, "max_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "max_webhook_secret", "")
    bot_dispatcher.reset()

    _, webhook = _app_with_webhook()

    assert webhook is None
    bot_dispatcher.reset()


async def test_webhook_is_not_registered_when_bot_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_enabled", False)
    monkeypatch.setattr(settings, "max_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "max_webhook_secret", WEBHOOK_SECRET)
    bot_dispatcher.reset()

    _, webhook = _app_with_webhook()

    assert webhook is None
    bot_dispatcher.reset()


async def test_webhook_requires_secret_header(configured_bot) -> None:
    """Раздел 41: без заголовка `X-Max-Bot-Api-Secret` — 403."""
    app, webhook = _app_with_webhook()
    assert webhook is not None

    async with _client(app) as client:
        response = await client.post("/webhook/max", json={"update_type": "unknown"})

    assert response.status_code == 403


async def test_webhook_rejects_wrong_secret(configured_bot) -> None:
    app, _ = _app_with_webhook()

    async with _client(app) as client:
        response = await client.post(
            "/webhook/max",
            json={"update_type": "unknown"},
            # Заголовок HTTP — только ASCII, поэтому секрет тоже латиницей
            headers={"X-Max-Bot-Api-Secret": "wrong-secret"},
        )

    assert response.status_code == 403


async def test_webhook_accepts_update_with_valid_secret(configured_bot) -> None:
    app, _ = _app_with_webhook()

    async with _client(app) as client:
        response = await client.post(
            "/webhook/max",
            json={"update_type": "unknown_update", "timestamp": 1},
            headers={"X-Max-Bot-Api-Secret": WEBHOOK_SECRET},
        )

    # Неизвестный тип обновления не ошибка транспорта: MAX получает подтверждение
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --- Регистрация webhook в MAX ----------------------------------------------


async def test_webhook_url_is_built_from_app_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_url", "https://example.com/")
    monkeypatch.setattr(settings, "max_webhook_path", "/webhook/max")
    monkeypatch.setattr(settings, "max_webhook_url", "")

    assert bot_webhook.webhook_url() == "https://example.com/webhook/max"


async def test_explicit_webhook_url_wins(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_webhook_url", "https://api.example.com/hook")

    assert bot_webhook.webhook_url() == "https://api.example.com/hook"


async def test_subscription_requires_https(monkeypatch) -> None:
    """Раздел 41: webhook работает только по HTTPS."""
    fake = _FakeBot()
    monkeypatch.setattr(bot_webhook, "get_bot", lambda: fake)
    monkeypatch.setattr(settings, "max_webhook_url", "http://example.com/webhook/max")

    await bot_webhook.subscribe_webhook()

    assert fake.subscriptions == []


async def test_subscription_passes_url_and_secret(monkeypatch) -> None:
    fake = _FakeBot()
    monkeypatch.setattr(bot_webhook, "get_bot", lambda: fake)
    monkeypatch.setattr(settings, "max_webhook_url", "https://example.com/webhook/max")
    monkeypatch.setattr(settings, "max_webhook_secret", WEBHOOK_SECRET)

    await bot_webhook.subscribe_webhook()

    assert fake.subscriptions == [("https://example.com/webhook/max", WEBHOOK_SECRET)]


async def test_subscription_failure_does_not_raise(monkeypatch) -> None:
    """Бот не должен мешать старту API."""

    class _BrokenBot(_FakeBot):
        async def subscribe_webhook(self, *, url: str, secret: str | None = None):
            raise RuntimeError("MAX недоступен")

    monkeypatch.setattr(bot_webhook, "get_bot", lambda: _BrokenBot())
    monkeypatch.setattr(settings, "max_webhook_url", "https://example.com/webhook/max")

    await bot_webhook.subscribe_webhook()


# --- Обработчики ------------------------------------------------------------


class _BotStartedEvent:
    def __init__(self, bot: _FakeBot, user_id: int | None) -> None:
        self.bot = bot
        self.user = type("User", (), {"user_id": user_id})()


class _MessageEvent:
    def __init__(self, bot: _FakeBot, user_id: int | None) -> None:
        self.bot = bot
        self._user_id = user_id

    def get_ids(self) -> tuple[int | None, int | None]:
        return 1, self._user_id


async def test_bot_started_answers_with_mini_app_link() -> None:
    fake = _FakeBot()

    await handle_bot_started(_BotStartedEvent(fake, 100500))

    assert fake.messages == [(100500, messages.bot_greeting())]


async def test_start_command_answers_with_mini_app_link() -> None:
    fake = _FakeBot()

    await handle_start_command(_MessageEvent(fake, 100501))

    assert fake.messages == [(100501, messages.bot_greeting())]


async def test_handler_without_user_id_does_nothing() -> None:
    fake = _FakeBot()

    await handle_start_command(_MessageEvent(fake, None))

    assert fake.messages == []


async def test_handler_survives_send_failure() -> None:
    """Падение обработчика ничего не исправит: MAX повторит доставку события."""
    fake = _FakeBot()
    fake.fail = True

    await handle_start_command(_MessageEvent(fake, 100502))

    assert fake.messages == []


# --- Остановка приложения ---------------------------------------------------


async def test_close_bot_releases_session(monkeypatch) -> None:
    """Раздел 51: при остановке ресурсы maxapi освобождаются."""
    closed: list[bool] = []

    class _Bot:
        async def close_session(self) -> None:
            closed.append(True)

    monkeypatch.setattr(bot_dispatcher, "_bot", _Bot())
    await bot_dispatcher.close_bot()

    assert closed == [True]
    assert bot_dispatcher.get_bot() is None or not settings.bot_enabled


async def test_close_bot_survives_broken_session(monkeypatch) -> None:
    class _Bot:
        async def close_session(self) -> None:
            raise RuntimeError("сессия уже закрыта")

    monkeypatch.setattr(bot_dispatcher, "_bot", _Bot())

    await bot_dispatcher.close_bot()


async def test_close_bot_without_bot_does_nothing() -> None:
    bot_dispatcher.reset()

    await bot_dispatcher.close_bot()
