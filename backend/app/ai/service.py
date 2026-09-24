"""Единая точка входа в ИИ. Раздел 58 тех-доки.

Бизнес-код (роутер) вызывает только `ai_service` и никогда не работает с
конкретным провайдером напрямую — по тому же принципу, что и
`NotificationService` для уведомлений (`app/notifications/service.py`).

Провайдеров текстовой генерации может быть несколько (`AI_PROVIDER_ORDER`):
это осознанное решение команды ради отказоустойчивости, а не ради качества
ответа — если первый провайдер недоступен или перегружен, пробуется
следующий по порядку. Если недоступны все, раздел 57 требует переход на
ручной ввод: сервис не поднимает исключение наружу, а возвращает
`ai_available=False`, и router отдаёт пустой черновик вместо ошибки.
"""

import json
import logging
from collections.abc import Sequence

from pydantic import ValidationError as PydanticValidationError

from app.ai.providers import (
    AIProviderError,
    SpeechToTextProvider,
    TextGenerationProvider,
)
from app.ai.schemas import (
    ParsedVacancyDraft,
    ParseVacancyResponse,
    TranscribeVacancyResponse,
)

logger = logging.getLogger("app.ai")

# Раздел 31: явный запрет на пол, возраст, фото и субъективные характеристики
# продублирован прямо в промпте — это не полагается только на то, что модель
# "и так не должна" их использовать.
#
# Проверка законности — не из тех-доки, продуктовое требование. Важно: это
# эвристика уровня LLM, а не техническая гарантия. Она защищает только
# AI-разбор (`parse-vacancy`/`transcribe-vacancy`); прямое создание вакансии
# через `POST /vacancies` (ручная форма, п.5.1 продуктового ТЗ) содержимое
# `title`/`description` никак не проверяет — модерации на уровне API нет.
# `legal`/`rejection_reason` — часть контракта ответа, а не только текст
# инструкции: так решение читается кодом, а не парсится из свободной фразы.
PARSE_SYSTEM_PROMPT = (
    "Ты помогаешь владельцу небольшого кафе, магазина или салона оформить "
    "вакансию для сервиса найма персонала.\n\n"
    "Сначала проверь законность описанной работы по законодательству РФ. "
    "Если текст описывает деятельность, запрещённую или уголовно/"
    "административно наказуемую в РФ — в частности (но не только) занятие "
    "проституцией и интим-услуги, распространение, хранение или перевозку "
    "наркотических и психотропных веществ, работу «закладчиком» или иным "
    "курьером запрещённых веществ, торговлю людьми, любую иную деятельность, "
    "прямо запрещённую законом, — НЕ извлекай поля вакансии. Верни СТРОГО "
    "один JSON-объект без пояснений и без markdown: "
    '{"legal": false, "rejection_reason": "<краткая причина на русском>"} '
    "и больше ничего.\n\n"
    "Если работа законна, извлеки из текста поля вакансии и верни СТРОГО "
    "один JSON-объект без пояснений, без markdown и без текста до или "
    "после: "
    '{"legal": true, "title": str|null, "company_name": str|null, '
    '"description": str|null, "location": str|null, "salary_min": '
    'number|null, "salary_max": number|null, "schedule": str|null, '
    '"criteria": [{"type": str, "required": bool, "value": object}], '
    '"questions": [{"question": str, "type": str}]}. '
    "Допустимые type критерия: location, schedule, salary, available_from, "
    "experience, certificate. Допустимые type вопроса: text, number, "
    "boolean, choice. Не придумывай данные, которых нет в тексте — оставляй "
    "поле null или пустой список. Никогда не используй пол, возраст, "
    "внешность, фото или иные личные характеристики кандидата."
)


class AIService:
    def __init__(
        self,
        *,
        text_providers: Sequence[TextGenerationProvider] = (),
        speech_providers: Sequence[SpeechToTextProvider] = (),
    ) -> None:
        self._text_providers = list(text_providers)
        self._speech_providers = list(speech_providers)

    def set_providers(
        self,
        *,
        text_providers: Sequence[TextGenerationProvider] | None = None,
        speech_providers: Sequence[SpeechToTextProvider] | None = None,
    ) -> None:
        """Подменяет провайдеров. Нужен тестам и композиции приложения."""
        if text_providers is not None:
            self._text_providers = list(text_providers)
        if speech_providers is not None:
            self._speech_providers = list(speech_providers)

    async def parse_vacancy(self, text: str) -> ParseVacancyResponse:
        raw, provider_name = await self._complete_with_failover(
            system_prompt=PARSE_SYSTEM_PROMPT, user_prompt=text
        )
        if raw is None:
            logger.warning("Ни один ИИ-провайдер не ответил на разбор вакансии")
            return ParseVacancyResponse(
                parsed=ParsedVacancyDraft(),
                source_text=text,
                provider=None,
                ai_available=False,
            )

        parsed, rejection_reason = _parse_draft(raw)
        return ParseVacancyResponse(
            parsed=parsed,
            source_text=text,
            provider=provider_name,
            ai_available=True,
            rejected=rejection_reason is not None,
            rejection_reason=rejection_reason,
        )

    async def transcribe_vacancy(
        self, *, audio: bytes, content_type: str
    ) -> TranscribeVacancyResponse:
        for provider in self._speech_providers:
            try:
                text = await provider.transcribe(
                    audio=audio, content_type=content_type
                )
            except AIProviderError:
                logger.warning(
                    "Провайдер распознавания речи %s недоступен",
                    provider.name,
                    exc_info=True,
                )
                continue
            return TranscribeVacancyResponse(text=text, provider=provider.name)

        logger.warning("Ни один провайдер распознавания речи не ответил")
        return TranscribeVacancyResponse(text="", provider=None)

    async def _complete_with_failover(
        self, *, system_prompt: str, user_prompt: str
    ) -> tuple[str | None, str | None]:
        for provider in self._text_providers:
            try:
                raw = await provider.complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
            except AIProviderError:
                logger.warning(
                    "Провайдер %s недоступен, пробуем следующего по порядку",
                    provider.name,
                    exc_info=True,
                )
                continue
            return raw, provider.name
        return None, None


def _parse_draft(raw: str) -> tuple[ParsedVacancyDraft, str | None]:
    """Раздел 57: невалидный JSON не должен ронять сценарий — пустой черновик
    возвращается вместо ошибки, экран подтверждения донаполняет пользователь.

    Возвращает `(черновик, причина отказа)`: причина не `None` — модель
    посчитала описанную работу незаконной (см. `PARSE_SYSTEM_PROMPT`), и
    черновик в этом случае всегда пустой независимо от того, что ещё
    прислала модель в том же объекте.
    """
    candidate = _extract_json_object(raw)
    if candidate is None:
        logger.warning("ИИ вернул невалидный JSON при разборе вакансии")
        return ParsedVacancyDraft(), None

    if candidate.get("legal") is False:
        reason = candidate.get("rejection_reason")
        reason = reason.strip() if isinstance(reason, str) and reason.strip() else (
            "Описание нарушает законодательство РФ"
        )
        logger.warning("ИИ отклонил текст вакансии как незаконный: %s", reason)
        return ParsedVacancyDraft(), reason

    try:
        return ParsedVacancyDraft.model_validate(candidate), None
    except PydanticValidationError:
        logger.warning("ИИ вернул JSON, не подходящий под схему вакансии")
        return ParsedVacancyDraft(), None


def _extract_json_object(raw: str) -> dict | None:
    """Модель иногда оборачивает JSON в markdown или добавляет пояснение —
    вырезаем содержимое между первой `{` и последней `}`."""
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass

    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_text_providers() -> list[TextGenerationProvider]:
    from app.ai.providers import GigaChatProvider, YandexGPTProvider
    from app.core.config import settings

    factories = {
        "gigachat": lambda: GigaChatProvider(
            auth_key=settings.gigachat_auth_key,
            scope=settings.gigachat_scope,
            oauth_url=settings.gigachat_oauth_url,
            api_url=settings.gigachat_api_url,
            model=settings.gigachat_model,
            timeout=settings.ai_request_timeout_seconds,
            verify_ssl=settings.gigachat_verify_ssl,
            ca_bundle_file=settings.gigachat_ca_bundle_path,
        ),
        "yandexgpt": lambda: YandexGPTProvider(
            api_key=settings.yandex_api_key,
            folder_id=settings.yandex_folder_id,
            model=settings.yandex_gpt_model,
            timeout=settings.ai_request_timeout_seconds,
        ),
    }
    order = [name for name in settings.ai_provider_order if name in factories]
    if not order:
        logger.warning(
            "AI_PROVIDER_ORDER не содержит известных провайдеров — используется "
            "порядок по умолчанию"
        )
        order = list(factories)
    return [factories[name]() for name in order]


def _build_speech_providers() -> list[SpeechToTextProvider]:
    from app.ai.providers import YandexSpeechKitProvider
    from app.core.config import settings

    return [
        YandexSpeechKitProvider(
            api_key=settings.yandex_speechkit_key,
            folder_id=settings.yandex_folder_id,
            lang=settings.yandex_speechkit_lang,
            timeout=settings.ai_request_timeout_seconds,
        )
    ]


def build_ai_service() -> AIService:
    """Собирает независимый экземпляр по текущей конфигурации (раздел 58)."""
    return AIService(
        text_providers=_build_text_providers(),
        speech_providers=_build_speech_providers(),
    )


# Единый экземпляр: бизнес-код обращается к нему, тесты подменяют провайдеров
ai_service = AIService()


def configure_ai_service() -> None:
    """Заполняет провайдеров `ai_service` по конфигурации.

    Вызывается из `app.main` при старте — в отличие от уведомлений
    (`build_transport`, вызывается лениво при первой отправке), провайдеров
    здесь несколько и порядок нужно собрать один раз, а не при каждом запросе.
    """
    ai_service.set_providers(
        text_providers=_build_text_providers(),
        speech_providers=_build_speech_providers(),
    )
