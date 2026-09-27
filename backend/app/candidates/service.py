"""Бизнес-логика профиля кандидата. Разделы 12, 14, 27 тех-доки."""

import logging
from pathlib import Path
from typing import Any

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.ai.schemas import ParseResumeResponse, ResumeParsedDraft
from app.ai.service import ai_service
from app.candidates.models import CandidateProfile
from app.candidates.schemas import CandidateProfileUpdateRequest
from app.core.database import utcnow
from app.core.errors import NotFoundError, ValidationError
from app.core.storage import (
    delete_file,
    detect_resume_mime,
    ensure_resume_size,
    extract_resume_text,
    resolve_stored_file,
    save_resume,
)
from app.skills import service as skills_service
from app.users.models import User

logger = logging.getLogger("app.candidates")


async def get_profile(user: User) -> CandidateProfile:
    """Профиль текущего кандидата.

    Профиль ищется по пользователю из сессии, поэтому чужой получить нельзя.
    """
    profile = await CandidateProfile.get_or_none(user_id=user.user_id)
    if profile is None:
        raise NotFoundError(
            "Профиль кандидата ещё не создан", code="candidate_profile_not_found"
        )
    return profile


async def save_profile(
    user: User, payload: CandidateProfileUpdateRequest
) -> CandidateProfile:
    """Создаёт профиль при первом обращении, дальше меняет существующий.

    Отдельного POST в разделе 27 нет: профиль связан с пользователем 1:1,
    поэтому создание — частный случай изменения.

    Исторические ответы первичного отбора (`screening_answers`) здесь не
    трогаются: они привязаны к отклику и остаются такими, какими были на
    момент отбора.
    """
    changes = payload.model_dump(exclude_unset=True)
    if "skill_ids" in changes:
        changes["skill_ids"] = await skills_service.validate_skill_ids(
            changes["skill_ids"]
        )

    profile = await CandidateProfile.get_or_none(user_id=user.user_id)
    if profile is None:
        return await _create_profile(user, changes)

    if not changes:
        return profile
    return await _apply_changes(profile, changes)


async def _create_profile(user: User, changes: dict[str, Any]) -> CandidateProfile:
    if not changes.get("desired_role"):
        # desired_role — NOT NULL, без него профиля не существует
        raise ValidationError(
            "Для создания профиля нужна желаемая должность",
            code="desired_role_required",
        )
    try:
        profile = await CandidateProfile.create(user_id=user.user_id, **changes)
    except IntegrityError:
        # Параллельный запрос успел создать профиль: применяем изменения к нему
        logger.info("Профиль кандидата уже создан параллельным запросом")
        existing = await CandidateProfile.get_or_none(user_id=user.user_id)
        if existing is None:
            raise
        return await _apply_changes(existing, changes)

    logger.info("Профиль кандидата создан")
    return profile


async def _apply_changes(
    profile: CandidateProfile, changes: dict[str, Any]
) -> CandidateProfile:
    for field, value in changes.items():
        setattr(profile, field, value)
    await profile.save(update_fields=[*changes.keys(), "updated_at"])
    return profile


async def set_resume(user: User, content: bytes) -> CandidateProfile:
    """Загружает или заменяет резюме (экран C11 UX-карты, функция 29).

    Профиль должен уже существовать: `desired_role` в `candidate_profiles`
    обязателен, поэтому резюме нельзя привязать раньше первого сохранения
    профиля — тот же порядок, что и у остальных полей кандидата.

    Текст извлекается сразу (best-effort, раздел 57): `resume_text` хранится
    для `parse_resume`, чтобы тот не читал файл заново.
    """
    profile = await get_profile(user)
    ensure_resume_size(len(content))
    mime = detect_resume_mime(content)
    new_path = save_resume(user.user_id, content, mime)
    text = extract_resume_text(content, mime)
    previous_path: str | None = None
    updated_at = utcnow()
    try:
        async with in_transaction() as connection:
            locked = await (
                CandidateProfile.filter(user_id=user.user_id)
                .using_db(connection)
                .select_for_update()
                .get()
            )
            previous_path = locked.resume_path
            locked.resume_path = str(new_path)
            locked.resume_text = text
            locked.resume_updated_at = updated_at
            await locked.save(
                using_db=connection,
                update_fields=[
                    "resume_path",
                    "resume_text",
                    "resume_updated_at",
                    "updated_at",
                ],
            )
    except Exception:
        delete_file(new_path)
        raise

    profile.resume_path = str(new_path)
    profile.resume_text = text
    profile.resume_updated_at = updated_at
    if previous_path:
        delete_file(previous_path)
    return profile


async def delete_resume(user: User) -> None:
    """Удаляет файл резюме и очищает поля. Отсутствие резюме — не ошибка."""
    profile = await get_profile(user)
    async with in_transaction() as connection:
        locked = await (
            CandidateProfile.filter(user_id=user.user_id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        previous_path = locked.resume_path
        if not previous_path:
            raise NotFoundError("Резюме не загружено", code="resume_not_found")

        locked.resume_path = None
        locked.resume_text = None
        locked.resume_updated_at = None
        await locked.save(
            using_db=connection,
            update_fields=[
                "resume_path",
                "resume_text",
                "resume_updated_at",
                "updated_at",
            ],
        )

    profile.resume_path = None
    profile.resume_text = None
    profile.resume_updated_at = None
    delete_file(previous_path)


def get_resume_file(profile: CandidateProfile) -> Path:
    """Путь к резюме текущего кандидата. Чужой файл получить нельзя: путь
    берётся из записи профиля сессии, дополнительно проверяется, что он
    лежит внутри хранилища."""
    path = resolve_stored_file(profile.resume_path)
    if path is None:
        raise NotFoundError("Резюме не загружено", code="resume_not_found")
    return path


async def parse_resume(user: User) -> ParseResumeResponse:
    """ИИ-черновик полей профиля из текста резюме (C11): результат никогда
    не сохраняется как истина без подтверждения — кандидат применяет его
    через `PATCH /candidate/profile` отдельным запросом."""
    profile = await get_profile(user)
    if not profile.resume_text:
        return ParseResumeResponse(
            parsed=ResumeParsedDraft(), provider=None, ai_available=False
        )
    return await _parse_resume_text(profile.resume_text)


async def parse_resume_draft(content: bytes) -> ParseResumeResponse:
    """Черновик полей профиля из присланного файла резюме — для кандидата,
    который ещё не создавал профиль (C11 до первого `PATCH /candidate/profile`,
    `candidate_profiles` пока не существует, а `desired_role` там NOT NULL).

    В отличие от `parse_resume`, ничего никуда не сохраняет: ни файл, ни
    извлечённый текст не привязываются к профилю. Подтверждение — тот же
    `PATCH /candidate/profile`, что и у остальных источников черновика; если
    кандидат позже захочет сохранить сам файл резюме, это отдельный
    `PATCH /candidate/resume`, который уже требует существующий профиль.
    """
    ensure_resume_size(len(content))
    mime = detect_resume_mime(content)
    text = extract_resume_text(content, mime)
    if not text:
        return ParseResumeResponse(
            parsed=ResumeParsedDraft(), provider=None, ai_available=False
        )
    return await _parse_resume_text(text)


async def _parse_resume_text(text: str) -> ParseResumeResponse:
    """Общая часть `parse_resume`/`parse_resume_draft`: ИИ-черновик полей +
    найденные навыки (экран «Найденные навыки», C11 UX-карты).

    Навыки ищутся отдельно от ИИ-разбора (`skills_service.suggest_skill_ids`)
    и подмешиваются в черновик всегда, даже если ни один ИИ-провайдер не
    ответил — это простое сопоставление с справочником, а не вызов ИИ
    (раздел 57: недоступность ИИ не должна ломать сценарий).
    """
    response = await ai_service.parse_resume(text)
    suggested = await skills_service.suggest_skill_ids(text)
    if suggested:
        response = response.model_copy(
            update={"parsed": response.parsed.model_copy(update={"skill_ids": suggested})}
        )
    return response
