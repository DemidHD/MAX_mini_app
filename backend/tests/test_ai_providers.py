"""Транспортный слой ИИ-провайдеров: форма запроса, разбор ответа, ошибки.

Реальные GigaChat/YandexGPT/SpeechKit недоступны из тестового окружения —
здесь проверяется код, а не сеть: `httpx.MockTransport` подменяет ответ
сервера, и провайдер настраивается на прямой `api_url`/`oauth_url`, минуя
DNS. Бизнес-логика (failover, JSON-схема) проверена в `test_ai.py` на фейках,
эти тесты — только про то, что сами клиенты правильно собирают запрос и не
падают необработанным исключением при плохом ответе.
"""

import httpx
import pytest

from app.ai.providers import (
    AIProviderUnavailableError,
    GigaChatProvider,
    YandexGPTProvider,
    YandexSpeechKitProvider,
)


_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(*args, **kwargs)

    return factory


# --- GigaChat --------------------------------------------------------------


async def test_gigachat_fetches_token_then_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/oauth":
            assert request.headers["Authorization"] == "Basic secret-key"
            return httpx.Response(200, json={"access_token": "tok-1", "expires_at": 0})
        assert request.headers["Authorization"] == "Bearer tok-1"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"title": "Бариста"}'}}]}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = GigaChatProvider(
        auth_key="secret-key",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://gigachat.test/oauth",
        api_url="https://gigachat.test/api",
        model="GigaChat",
        timeout=5,
    )

    result = await provider.complete(system_prompt="sys", user_prompt="user")

    assert result == '{"title": "Бариста"}'
    assert len(calls) == 2


async def test_gigachat_without_auth_key_is_unavailable() -> None:
    provider = GigaChatProvider(
        auth_key="",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://gigachat.test/oauth",
        api_url="https://gigachat.test/api",
        model="GigaChat",
        timeout=5,
    )
    with pytest.raises(AIProviderUnavailableError):
        await provider.complete(system_prompt="sys", user_prompt="user")


async def test_gigachat_raises_on_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth":
            return httpx.Response(200, json={"access_token": "tok-1"})
        return httpx.Response(200, json={"unexpected": "shape"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = GigaChatProvider(
        auth_key="secret-key",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://gigachat.test/oauth",
        api_url="https://gigachat.test/api",
        model="GigaChat",
        timeout=5,
    )

    with pytest.raises(AIProviderUnavailableError):
        await provider.complete(system_prompt="sys", user_prompt="user")


async def test_gigachat_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = GigaChatProvider(
        auth_key="secret-key",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://gigachat.test/oauth",
        api_url="https://gigachat.test/api",
        model="GigaChat",
        timeout=5,
    )

    with pytest.raises(AIProviderUnavailableError):
        await provider.complete(system_prompt="sys", user_prompt="user")


# --- YandexGPT ---------------------------------------------------------------


async def test_yandexgpt_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={"result": {"alternatives": [{"message": {"text": '{"title": "Повар"}'}}]}},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = YandexGPTProvider(
        api_key="api-key",
        folder_id="folder-1",
        api_url="https://yandexgpt.test/completion",
        model="yandexgpt",
        timeout=5,
    )

    result = await provider.complete(system_prompt="sys", user_prompt="user")

    assert result == '{"title": "Повар"}'
    assert captured["headers"]["Authorization"] == "Api-Key api-key"
    assert captured["headers"]["x-folder-id"] == "folder-1"
    assert b"gpt://folder-1/yandexgpt" in captured["body"]


async def test_yandexgpt_without_credentials_is_unavailable() -> None:
    provider = YandexGPTProvider(
        api_key="", folder_id="", api_url="https://yandexgpt.test", model="m", timeout=5
    )
    with pytest.raises(AIProviderUnavailableError):
        await provider.complete(system_prompt="sys", user_prompt="user")


# --- Yandex SpeechKit ----------------------------------------------------------


async def test_speechkit_sends_audio_and_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Api-Key stt-key"
        assert request.url.params["lang"] == "ru-RU"
        assert request.content == b"raw-audio"
        return httpx.Response(200, json={"result": "текст распознан"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = YandexSpeechKitProvider(
        api_key="stt-key",
        folder_id="",
        api_url="https://stt.test/recognize",
        lang="ru-RU",
        timeout=5,
    )

    result = await provider.transcribe(audio=b"raw-audio", content_type="audio/ogg")

    assert result == "текст распознан"


async def test_speechkit_without_key_is_unavailable() -> None:
    provider = YandexSpeechKitProvider(
        api_key="", folder_id="", api_url="https://stt.test", lang="ru-RU", timeout=5
    )
    with pytest.raises(AIProviderUnavailableError):
        await provider.transcribe(audio=b"data", content_type="audio/ogg")
