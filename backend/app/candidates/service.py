"""Бизнес-логика профиля кандидата. Разделы 12, 14, 27 тех-доки."""

import logging
from typing import Any

from tortoise.exceptions import IntegrityError

from app.candidates.models import CandidateProfile
from app.candidates.schemas import CandidateProfileUpdateRequest
from app.core.errors import NotFoundError, ValidationError
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
