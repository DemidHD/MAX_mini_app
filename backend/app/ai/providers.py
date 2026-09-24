"""Клиенты внешних ИИ-провайдеров. Раздел 58 тех-доки.

Через официальные SDK (`gigachat`, `yandex-ai-studio-sdk`), а не голый HTTP:
они сами делают OAuth/токены, повторы и разбор ответа — это меньше кода для
поддержки, чем ручной клиент поверх httpx. Ни один из классов не знает про
вакансии, JSON-схему черновика или домен вообще — это (`AIService`,
`app/ai/service.py`) явно требует раздел 58: "конкретный provider не должен
быть связан с domain logic".

Два провайдера текстовой генерации (GigaChat, YandexGPT) существуют
одновременно не ради качества ответа, а ради отказоустойчивости: если один
провайдер лёг или перегружен, `AIService` пробует следующего по списку
`AI_PROVIDER_ORDER`. Голосовой ввод расшифровывает только Yandex SpeechKit —
специализированный сервис распознавания речи, у GigaChat прямого аналога нет.
"""

import logging
from typing import Protocol, runtime_checkable

import httpx
from gigachat import GigaChat
from gigachat.exceptions import GigaChatException
from gigachat.models import Chat, Messages, MessagesRole
from yandex_ai_studio_sdk import AsyncAIStudio
from yandex_ai_studio_sdk.exceptions import AioRpcError, AIStudioError

# Публично SDK отдаёт enum только через инстанс (`sdk.speechkit.AudioFormat`),
# но это тот же объект, что и здесь — импорт напрямую не тянет клиент за собой.
from yandex_ai_studio_sdk._speechkit.enums import AudioFormat

logger = logging.getLogger("app.ai")


class AIProviderError(Exception):
    """Провайдер не смог ответить. `AIService` пробует следующего по порядку."""


class AIProviderUnavailableError(AIProviderError):
    """Не настроен, сеть/таймаут, ошибка авторизации, 5xx — временно недоступен."""


@runtime_checkable
class TextGenerationProvider(Protocol):
    """Минимум, который нужен `AIService.parse_vacancy`."""

    name: str

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Текст ответа модели. Бросает `AIProviderError`, если ответа нет."""


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """Минимум, который нужен `AIService.transcribe_vacancy`."""

    name: str

    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        """Распознанный текст. Бросает `AIProviderError`, если ответа нет."""


class GigaChatProvider:
    """GigaChat API (Sber) через официальный пакет `gigachat`.

    https://developers.sber.ru/docs/ru/gigachat/api/overview
    """

    name = "gigachat"

    def __init__(
        self,
        *,
        auth_key: str,
        scope: str,
        oauth_url: str,
        api_url: str,
        model: str,
        timeout: float,
        verify_ssl: bool = True,
        ca_bundle_file: str = "",
    ) -> None:
        self._auth_key = auth_key
        self._scope = scope
        self._oauth_url = oauth_url
        self._api_url = api_url
        self._model = model
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._ca_bundle_file = ca_bundle_file or None

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self._auth_key:
            raise AIProviderUnavailableError("GigaChat не настроен")

        chat = Chat(
            model=self._model,
            temperature=0.1,
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(role=MessagesRole.USER, content=user_prompt),
            ],
        )
        try:
            async with GigaChat(
                base_url=self._api_url,
                auth_url=self._oauth_url,
                credentials=self._auth_key,
                scope=self._scope,
                model=self._model,
                timeout=self._timeout,
                verify_ssl_certs=self._verify_ssl,
                ca_bundle_file=self._ca_bundle_file,
            ) as client:
                completion = await client.achat(chat)
        except (GigaChatException, httpx.HTTPError, OSError) as error:
            raise AIProviderUnavailableError(f"GigaChat недоступен: {error}") from error

        try:
            return completion.choices[0].message.content
        except (IndexError, AttributeError) as error:
            raise AIProviderUnavailableError(
                f"GigaChat вернул неожиданный ответ: {error}"
            ) from error


class YandexGPTProvider:
    """YandexGPT через официальный `yandex-ai-studio-sdk`.

    https://yandex.cloud/ru/docs/foundation-models/
    """

    name = "yandexgpt"

    def __init__(self, *, api_key: str, folder_id: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._folder_id = folder_id
        self._model = model
        self._timeout = timeout

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self._api_key or not self._folder_id:
            raise AIProviderUnavailableError("YandexGPT не настроен")

        sdk = AsyncAIStudio(folder_id=self._folder_id, auth=self._api_key)
        try:
            model = sdk.models.completions(self._model).configure(temperature=0.1)
            result = await model.run(
                [
                    {"role": "system", "text": system_prompt},
                    {"role": "user", "text": user_prompt},
                ],
                timeout=self._timeout,
            )
        except (AIStudioError, AioRpcError, OSError) as error:
            raise AIProviderUnavailableError(f"YandexGPT недоступен: {error}") from error

        try:
            return result[0].text
        except (IndexError, AttributeError) as error:
            raise AIProviderUnavailableError(
                f"YandexGPT вернул неожиданный ответ: {error}"
            ) from error


class YandexSpeechKitProvider:
    """Yandex SpeechKit через официальный `yandex-ai-studio-sdk`.

    https://yandex.cloud/ru/docs/speechkit/stt/
    """

    name = "yandex_speechkit"

    # Формат приходит из `UploadFile.content_type`; нераспознанный тип
    # пробуем как OGG_OPUS — самый частый контейнер голосовых сообщений.
    _AUDIO_FORMATS = {
        "audio/ogg": AudioFormat.OGG_OPUS,
        "audio/opus": AudioFormat.OGG_OPUS,
        "audio/mpeg": AudioFormat.MP3,
        "audio/mp3": AudioFormat.MP3,
        "audio/wav": AudioFormat.WAV,
        "audio/x-wav": AudioFormat.WAV,
        "audio/wave": AudioFormat.WAV,
    }

    def __init__(self, *, api_key: str, folder_id: str, lang: str, timeout: float) -> None:
        self._api_key = api_key
        self._folder_id = folder_id
        self._lang = lang
        self._timeout = timeout

    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        if not self._api_key:
            raise AIProviderUnavailableError("SpeechKit не настроен")

        audio_format = self._AUDIO_FORMATS.get(
            content_type.split(";", 1)[0].strip().lower(), AudioFormat.OGG_OPUS
        )
        sdk = AsyncAIStudio(folder_id=self._folder_id, auth=self._api_key)
        try:
            stt = sdk.speechkit.stt(audio_format=audio_format, language_codes=self._lang)
            result = await stt.run(audio, timeout=self._timeout)
        except (AIStudioError, AioRpcError, OSError) as error:
            raise AIProviderUnavailableError(f"SpeechKit недоступен: {error}") from error

        text = result.text
        if not text:
            raise AIProviderUnavailableError("SpeechKit не распознал текст")
        return text
