"""ИИ: разбор вакансии текстом/голосом. Раздел 58 тех-доки.

Два провайдера текстовой генерации существуют ради отказоустойчивости
(команда сознательно выбрала GigaChat + YandexGPT с failover, а не один
провайдер), а не ради выбора лучшего ответа — раздел 57 требует, чтобы
недоступность ИИ переключала сценарий на ручной ввод, а не рушила запрос.
Тесты подменяют провайдеров фейками: реальные GigaChat/YandexGPT/SpeechKit
не настроены и не должны быть настроены в тестовом окружении.
"""

from itertools import count
from typing import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.providers import AIProviderUnavailableError
from app.ai.service import ai_service
from app.core.enums import UserRole
from app.main import app
from app.users.models import User
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(900000)
_candidate_ids = count(901000)


class _FakeTextProvider:
    def __init__(self, name: str, *, raises: bool = False, response: str = "{}") -> None:
        self.name = name
        self._raises = raises
        self._response = response
        self.calls = 0

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self._raises:
            raise AIProviderUnavailableError(f"{self.name} недоступен")
        return self._response


class _FakeSpeechProvider:
    def __init__(self, name: str, *, raises: bool = False, text: str = "текст") -> None:
        self.name = name
        self._raises = raises
        self._text = text

    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        if self._raises:
            raise AIProviderUnavailableError(f"{self.name} недоступен")
        return self._text


@pytest.fixture(autouse=True)
def _reset_ai_providers() -> Iterator[None]:
    """Провайдеры ИИ — общий singleton процесса: не должны утекать в другие тесты."""
    yield
    ai_service.set_providers(text_providers=[], speech_providers=[])


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> None:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)


async def _employer(client: AsyncClient) -> None:
    await _login(client, next(_employer_ids), UserRole.EMPLOYER)


def _fresh_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Разбор вакансии: отказоустойчивость между провайдерами --------------------


async def test_parse_vacancy_uses_first_available_provider(client: AsyncClient) -> None:
    await _employer(client)
    ai_service.set_providers(
        text_providers=[
            _FakeTextProvider(
                "gigachat", response='{"title": "Бариста", "location": "Москва"}'
            )
        ]
    )

    response = await client.post(
        "/api/ai/parse-vacancy", json={"text": "Ищем бариста в Москве"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_available"] is True
    assert body["provider"] == "gigachat"
    assert body["parsed"]["title"] == "Бариста"
    assert body["parsed"]["location"] == "Москва"
    assert body["source_text"] == "Ищем бариста в Москве"


async def test_parse_vacancy_falls_over_to_second_provider(client: AsyncClient) -> None:
    """Раздел 57: недоступность одного провайдера не должна давать отказ пользователю."""
    await _employer(client)
    down = _FakeTextProvider("gigachat", raises=True)
    up = _FakeTextProvider("yandexgpt", response='{"title": "Повар"}')
    ai_service.set_providers(text_providers=[down, up])

    response = await client.post("/api/ai/parse-vacancy", json={"text": "Нужен повар"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_available"] is True
    assert body["provider"] == "yandexgpt"
    assert body["parsed"]["title"] == "Повар"
    assert down.calls == 1


async def test_parse_vacancy_all_providers_down_falls_back_to_manual(
    client: AsyncClient,
) -> None:
    """Раздел 57: AI unavailable -> переход на ручной ввод, не ошибка."""
    await _employer(client)
    ai_service.set_providers(
        text_providers=[
            _FakeTextProvider("gigachat", raises=True),
            _FakeTextProvider("yandexgpt", raises=True),
        ]
    )

    response = await client.post("/api/ai/parse-vacancy", json={"text": "Нужен официант"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_available"] is False
    assert body["provider"] is None
    assert body["parsed"] == {
        "title": None,
        "company_name": None,
        "description": None,
        "location": None,
        "salary_min": None,
        "salary_max": None,
        "schedule": None,
        "criteria": [],
        "questions": [],
    }


async def test_parse_vacancy_invalid_json_does_not_publish_and_does_not_fail(
    client: AsyncClient,
) -> None:
    """Раздел 57: невалидный JSON — пустой черновик, а не 5xx."""
    await _employer(client)
    ai_service.set_providers(
        text_providers=[_FakeTextProvider("gigachat", response="это не JSON вообще")]
    )

    response = await client.post("/api/ai/parse-vacancy", json={"text": "..."})
    assert response.status_code == 200, response.text
    body = response.json()
    # Провайдер ответил — это не «недоступность», просто нечего извлечь
    assert body["ai_available"] is True
    assert body["provider"] == "gigachat"
    assert body["parsed"]["title"] is None


async def test_parse_vacancy_extracts_json_wrapped_in_markdown(client: AsyncClient) -> None:
    await _employer(client)
    wrapped = (
        'Вот структура:\n```json\n{"title": "Кассир", "schedule": "2/2"}\n```\nГотово.'
    )
    ai_service.set_providers(text_providers=[_FakeTextProvider("gigachat", response=wrapped)])

    response = await client.post("/api/ai/parse-vacancy", json={"text": "..."})
    assert response.status_code == 200, response.text
    parsed = response.json()["parsed"]
    assert parsed["title"] == "Кассир"
    assert parsed["schedule"] == "2/2"


async def test_parse_vacancy_rejects_disallowed_criterion_type(client: AsyncClient) -> None:
    """Раздел 31: у схемы черновика просто нет типа критерия под личные признаки."""
    await _employer(client)
    raw = '{"title": "Бариста", "criteria": [{"type": "gender", "required": true, "value": {}}]}'
    ai_service.set_providers(text_providers=[_FakeTextProvider("gigachat", response=raw)])

    response = await client.post("/api/ai/parse-vacancy", json={"text": "..."})
    assert response.status_code == 200, response.text
    body = response.json()
    # Схема не знает типа "gender" — весь черновик не проходит валидацию, и
    # backend отдаёт пустой, а не протаскивает недопустимое поле молча
    assert body["parsed"]["title"] is None
    assert body["parsed"]["criteria"] == []


async def test_parse_vacancy_access_control(client: AsyncClient) -> None:
    async with _fresh_client() as guest:
        assert (
            await guest.post("/api/ai/parse-vacancy", json={"text": "x"})
        ).status_code == 401

    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    wrong_role = await client.post("/api/ai/parse-vacancy", json={"text": "x"})
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"


async def test_parse_vacancy_validates_text_length(client: AsyncClient) -> None:
    await _employer(client)
    assert (
        await client.post("/api/ai/parse-vacancy", json={"text": ""})
    ).status_code == 422


# --- Голосовой ввод --------------------------------------------------------------


async def test_transcribe_vacancy_uses_available_provider(client: AsyncClient) -> None:
    await _employer(client)
    ai_service.set_providers(
        speech_providers=[
            _FakeSpeechProvider("yandex_speechkit", text="Ищем бариста на полный день")
        ]
    )

    response = await client.post(
        "/api/ai/transcribe-vacancy",
        files={"file": ("voice.ogg", b"fake-audio-bytes", "audio/ogg")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Ищем бариста на полный день"
    assert body["provider"] == "yandex_speechkit"


async def test_transcribe_vacancy_falls_back_when_provider_down(
    client: AsyncClient,
) -> None:
    """Раздел 57: недоступность распознавания — тоже переход на ручной ввод."""
    await _employer(client)
    ai_service.set_providers(
        speech_providers=[_FakeSpeechProvider("yandex_speechkit", raises=True)]
    )

    response = await client.post(
        "/api/ai/transcribe-vacancy",
        files={"file": ("voice.ogg", b"fake-audio-bytes", "audio/ogg")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == ""
    assert body["provider"] is None


async def test_transcribe_vacancy_rejects_empty_file(client: AsyncClient) -> None:
    await _employer(client)
    response = await client.post(
        "/api/ai/transcribe-vacancy",
        files={"file": ("voice.ogg", b"", "audio/ogg")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_file"


async def test_transcribe_vacancy_requires_employer(client: AsyncClient) -> None:
    async with _fresh_client() as guest:
        response = await guest.post(
            "/api/ai/transcribe-vacancy",
            files={"file": ("voice.ogg", b"fake-audio-bytes", "audio/ogg")},
        )
    assert response.status_code == 401
