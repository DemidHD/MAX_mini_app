"""Интеграция с MAX на моках. Разделы 40-45, 49, 51 тех-доки.

Остальные тесты подменяют канал уведомлений целиком, поэтому боевой путь
`NotificationService → MaxBotTransport → maxapi.Bot` и путь `MAX → webhook →
диспетчер → обработчик` в них не участвуют. Здесь проверяются именно они:
вместо MAX подставлен мок бота, всё остальное — настоящий код.
"""

import time
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.bot import dispatcher as bot_dispatcher
from app.bot import webhook as bot_webhook
from app.core.config import settings
from app.core.enums import NotificationStatus, NotificationType
from app.notifications import messages
from app.notifications.models import NotificationLog
from app.notifications.service import NotificationService
from app.notifications.transport import (
    DisabledTransport,
    MaxBotTransport,
    NotificationsDisabledError,
    build_transport,
)
from app.users.models import User

WEBHOOK_SECRET = "integration-webhook-secret"
BOT_USER_ID = 850001
CANDIDATE_USER_ID = 850002


class MaxBotMock:
    """Мок `maxapi.Bot`: запоминает вызовы вместо обращения к MAX Bot API.

    Сигнатуры повторяют библиотечные — если они изменятся, тесты должны
    падать здесь, а не в бою.
    """

    # `maxapi` спрашивает это поле у бота, когда обогащает событие: с False
    # библиотека не ходит в API за чатом и пользователем
    auto_requests = False
    # Профиль бота заполняет `dp.startup` при запуске приложения; фильтр
    # команд умеет работать и без него
    me = None

    def __init__(self, *, error: Exception | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.error = error

    async def send_message(
        self, *, user_id: int | None = None, text: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        self.sent.append({"user_id": user_id, "text": text, **kwargs})
        return {"message": {"body": {"mid": f"mid.{len(self.sent)}"}}}

    async def close_session(self) -> None:
        self.closed = True


@pytest_asyncio.fixture
async def bot_mock(monkeypatch) -> AsyncIterator[MaxBotMock]:
    """Настроенный бот, у которого вместо MAX — мок."""
    mock = MaxBotMock()
    monkeypatch.setattr(settings, "bot_enabled", True)
    monkeypatch.setattr(settings, "max_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "max_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "max_webhook_path", "/webhook/max")
    monkeypatch.setattr(bot_dispatcher, "_bot", mock)
    monkeypatch.setattr(bot_dispatcher, "_dispatcher", None)
    yield mock
    bot_dispatcher.reset()


@pytest_asyncio.fixture
async def webhook_client(bot_mock: MaxBotMock) -> AsyncIterator[AsyncClient]:
    """Приложение с подключённым webhook'ом бота."""
    app = FastAPI()
    assert bot_webhook.setup_bot_webhook(app) is not None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def _now_ms() -> int:
    return int(time.time() * 1000)


def _max_user(user_id: int) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "first_name": "Иван",
        "is_bot": False,
        "last_activity_time": _now_ms(),
    }


def bot_started_update(user_id: int) -> dict[str, Any]:
    """Обновление, которое MAX присылает при открытии диалога с ботом."""
    return {
        "update_type": "bot_started",
        "timestamp": _now_ms(),
        "chat_id": 777001,
        "user": _max_user(user_id),
        "user_locale": "ru",
    }


def message_update(user_id: int, text: str) -> dict[str, Any]:
    """Обновление о новом сообщении в диалоге с ботом."""
    moment = _now_ms()
    return {
        "update_type": "message_created",
        "timestamp": moment,
        "message": {
            "sender": _max_user(user_id),
            "recipient": {"chat_id": 777001, "chat_type": "dialog", "user_id": user_id},
            "timestamp": moment,
            "body": {"mid": "mid.000001", "seq": 1, "text": text},
        },
        "user_locale": "ru",
    }


async def _deliver(client: AsyncClient, update: dict[str, Any]):
    return await client.post(
        "/webhook/max",
        json=update,
        headers={"X-Max-Bot-Api-Secret": WEBHOOK_SECRET},
    )


# --- MAX → webhook → диспетчер → обработчик ---------------------------------


async def test_webhook_routing_flow(
    webhook_client: AsyncClient, bot_mock: MaxBotMock
) -> None:
    # 1. Открытие диалога отвечает приветствием со ссылкой на Mini App (раздел 43)
    started = await _deliver(webhook_client, bot_started_update(BOT_USER_ID))
    assert started.status_code == 200, started.text
    assert bot_mock.sent == [{"user_id": BOT_USER_ID, "text": messages.bot_greeting()}]
    bot_mock.sent.clear()

    # 2. /start отвечает тем же приветствием
    start_command = await _deliver(webhook_client, message_update(BOT_USER_ID, "/start"))
    assert start_command.status_code == 200, start_command.text
    assert [item["user_id"] for item in bot_mock.sent] == [BOT_USER_ID]
    assert "Открыть приложение" in bot_mock.sent[0]["text"]
    bot_mock.sent.clear()

    # 3. Бот в P0 не ведёт переписку: на обычные сообщения он не отвечает
    other = await _deliver(webhook_client, message_update(BOT_USER_ID, "здравствуйте"))
    assert other.status_code == 200
    assert bot_mock.sent == []

    # 4. Незнакомый тип обновления подтверждается без повторной доставки
    unknown = await _deliver(
        webhook_client, {"update_type": "dialog_muted", "timestamp": _now_ms()}
    )
    assert unknown.status_code == 200
    assert unknown.json() == {"ok": True}

    # 5. Раздел 41: без секрета обновление не обрабатывается вовсе
    no_secret = await webhook_client.post(
        "/webhook/max", json=bot_started_update(BOT_USER_ID)
    )
    assert no_secret.status_code == 403
    assert bot_mock.sent == []

    # 6. Ошибка отправки не превращается в 500: MAX сам повторит доставку
    bot_mock.error = RuntimeError("MAX недоступен")
    failing = await _deliver(webhook_client, bot_started_update(BOT_USER_ID))
    assert failing.status_code == 200


# --- NotificationService → MaxBotTransport → maxapi.Bot ----------------------


async def test_transport_sends_through_bot(bot_mock: MaxBotMock) -> None:
    """Боевой транспорт вызывает `send_message` по `user_id` (раздел 45)."""
    await MaxBotTransport().send(CANDIDATE_USER_ID, "Собеседование назначено")

    assert bot_mock.sent == [
        {"user_id": CANDIDATE_USER_ID, "text": "Собеседование назначено"}
    ]


async def test_transport_propagates_api_error(bot_mock: MaxBotMock) -> None:
    """Ошибку MAX транспорт не глотает: решение о повторе принимает сервис."""
    bot_mock.error = RuntimeError("500 Internal Server Error")

    with pytest.raises(RuntimeError):
        await MaxBotTransport().send(CANDIDATE_USER_ID, "текст")


async def test_transport_without_bot_reports_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_enabled", False)
    bot_dispatcher.reset()

    with pytest.raises(NotificationsDisabledError):
        await MaxBotTransport().send(CANDIDATE_USER_ID, "текст")


def test_build_transport_follows_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_enabled", True)
    monkeypatch.setattr(settings, "max_bot_token", "test-bot-token")
    assert isinstance(build_transport(), MaxBotTransport)

    monkeypatch.setattr(settings, "bot_enabled", False)
    assert isinstance(build_transport(), DisabledTransport)

    monkeypatch.setattr(settings, "bot_enabled", True)
    monkeypatch.setattr(settings, "max_bot_token", "")
    assert isinstance(build_transport(), DisabledTransport)


async def test_notification_goes_through_real_transport(
    bot_mock: MaxBotMock, monkeypatch
) -> None:
    """Сквозная проверка боевого пути уведомления, без подмены транспорта."""
    monkeypatch.setattr(settings, "notification_retry_delay_seconds", 0)
    user = await User.get_or_none(user_id=CANDIDATE_USER_ID) or await User.create(
        user_id=CANDIDATE_USER_ID, first_name="Кандидат"
    )
    await NotificationLog.filter(user_id=user.user_id).delete()

    service = NotificationService()
    await service.candidate_invited(
        candidate_id=user.user_id, application_id=9001, vacancy_title="Бариста"
    )

    assert len(bot_mock.sent) == 1
    assert "Бариста" in bot_mock.sent[0]["text"]
    log = await NotificationLog.get(
        event_type=NotificationType.CANDIDATE_INVITED,
        entity_id=9001,
        user_id=user.user_id,
    )
    assert log.status is NotificationStatus.SENT


async def test_retry_reaches_max_after_temporary_error(
    bot_mock: MaxBotMock, monkeypatch
) -> None:
    """Раздел 49: временная ошибка MAX приводит к повторной отправке."""
    monkeypatch.setattr(settings, "notification_retry_delay_seconds", 0)
    user = await User.get_or_none(user_id=CANDIDATE_USER_ID) or await User.create(
        user_id=CANDIDATE_USER_ID, first_name="Кандидат"
    )
    await NotificationLog.filter(user_id=user.user_id).delete()

    attempts = {"count": 0}
    original = bot_mock.send_message

    async def _flaky(**kwargs: Any):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("503 Service Unavailable")
        return await original(**kwargs)

    monkeypatch.setattr(bot_mock, "send_message", _flaky)

    service = NotificationService()
    await service.application_created(
        employer_id=user.user_id, application_id=9002, vacancy_title="Бариста"
    )

    assert attempts["count"] == 2
    assert len(bot_mock.sent) == 1
    log = await NotificationLog.get(
        event_type=NotificationType.APPLICATION_CREATED, entity_id=9002
    )
    assert log.status is NotificationStatus.SENT
    assert log.attempts == 2


async def test_bot_session_is_closed_on_shutdown(bot_mock: MaxBotMock) -> None:
    """Раздел 51: при остановке приложения ресурсы освобождаются."""
    await bot_dispatcher.close_bot()

    assert bot_mock.closed is True
