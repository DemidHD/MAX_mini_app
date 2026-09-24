"""Эндпоинты ИИ. Раздел 27 (список), 58 тех-доки.

Оба эндпоинта — вспомогательные для создания вакансии, поэтому доступны
только работодателю: раздел 28 отдаёт саму публикацию `POST /vacancies`,
а эти лишь помогают предзаполнить форму (продуктовое ТЗ, п. 5.1). Ни один
из них не создаёт и не публикует вакансию — это делает существующий
эндпоинт, куда frontend отправляет отредактированный черновик.
"""

import logging

from fastapi import APIRouter, File, UploadFile

from app.ai.schemas import (
    ParseVacancyRequest,
    ParseVacancyResponse,
    TranscribeVacancyResponse,
)
from app.ai.service import ai_service
from app.auth.dependencies import EmployerUser
from app.core.errors import ValidationError

logger = logging.getLogger("app.ai")

router = APIRouter(prefix="/ai", tags=["ai"])

# Значение не из тех-доки — раздел 58 не задаёт лимит голосового ввода,
# он нужен как защита от мусорного тела запроса, а не продуктовая настройка.
MAX_AUDIO_SIZE_BYTES = 15 * 1024 * 1024


@router.post("/parse-vacancy", response_model=ParseVacancyResponse)
async def parse_vacancy(
    payload: ParseVacancyRequest, _: EmployerUser
) -> ParseVacancyResponse:
    """Разбирает свободный текст вакансии в черновик полей (раздел 58).

    Черновик не публикуется и не сохраняется — работодатель правит его на
    экране подтверждения и отправляет уже как обычный `POST /vacancies`.
    """
    return await ai_service.parse_vacancy(payload.text)


@router.post("/transcribe-vacancy", response_model=TranscribeVacancyResponse)
async def transcribe_vacancy(
    _: EmployerUser, file: UploadFile = File(...)
) -> TranscribeVacancyResponse:
    """Расшифровывает голосовое описание вакансии в текст (раздел 58).

    Результат — обычный текст, который frontend передаёт тем же путём, что и
    напечатанный, в `POST /ai/parse-vacancy`. Аудио нигде не сохраняется.
    """
    if file.size is not None:
        _ensure_audio_size(file.size)
    content = await file.read(MAX_AUDIO_SIZE_BYTES + 1)
    _ensure_audio_size(len(content))

    return await ai_service.transcribe_vacancy(
        audio=content, content_type=file.content_type or "application/octet-stream"
    )


def _ensure_audio_size(size: int) -> None:
    if size == 0:
        raise ValidationError("Аудио пустое", code="empty_file")
    if size > MAX_AUDIO_SIZE_BYTES:
        raise ValidationError(
            f"Максимальный размер аудио — {MAX_AUDIO_SIZE_BYTES} байт",
            code="file_too_large",
        )
