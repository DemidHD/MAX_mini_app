"""Авторизация через MAX и серверные сессии. Разделы 6, 7, 10 тех-доки."""

import logging
from datetime import timedelta
from uuid import UUID

from app.applications.models import Application
from app.auth.init_data import InitData, MaxUser, validate_init_data
from app.auth.models import Session
from app.candidates.models import CandidateProfile
from app.core.config import settings
from app.core.database import utcnow
from app.core.enums import ApplicationStatus, UserRole
from app.users.models import User
from app.vacancies.models import Vacancy

logger = logging.getLogger("app.auth")

# Отклики, по которым сценарий кандидата ещё продолжается: на них возвращаем
# пользователя при повторном открытии Mini App.
ACTIVE_APPLICATION_STATUSES = (
    ApplicationStatus.CREATED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.PASSED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.INVITED,
    ApplicationStatus.MUTUAL_INTEREST,
    ApplicationStatus.INTERVIEW_SCHEDULED,
)


async def authenticate(init_data_raw: str) -> tuple[User, Session]:
    """Проверяет initData, создаёт или обновляет пользователя и открывает сессию."""
    init_data: InitData = validate_init_data(
        init_data_raw,
        bot_token=settings.max_bot_token,
        max_age_seconds=settings.auth_date_max_age_seconds,
    )
    user = await _upsert_user(init_data.user)
    session = await Session.create(
        user=user,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    return user, session


async def _upsert_user(max_user: MaxUser) -> User:
    """Создаёт пользователя при первом входе, иначе обновляет актуальные данные.

    Имя и фамилия при повторном входе не перезаписываются: пользователь мог
    изменить их внутри MAX Найм (раздел 7).
    """
    user = await User.get_or_none(user_id=max_user.user_id)
    if user is None:
        return await User.create(
            user_id=max_user.user_id,
            first_name=max_user.first_name,
            last_name=max_user.last_name,
            username=max_user.username,
            language_code=max_user.language_code,
        )

    user.username = max_user.username
    user.language_code = max_user.language_code
    user.last_auth_at = utcnow()
    await user.save(update_fields=["username", "language_code", "last_auth_at", "updated_at"])
    return user


async def get_session_user(raw_session_id: str) -> User | None:
    """Возвращает пользователя действующей сессии; просроченную сессию удаляет."""
    try:
        session_id = UUID(raw_session_id)
    except ValueError:
        return None

    session = await Session.get_or_none(id=session_id).select_related("user")
    if session is None:
        return None

    if session.is_expired():
        await session.delete()
        return None

    session.last_used_at = utcnow()
    await session.save(update_fields=["last_used_at"])
    return session.user


async def compute_current_step(user: User) -> tuple[str, int | None]:
    """Шаг сценария, на который нужно вернуть пользователя (раздел 7).

    Значение вычисляется из текущего состояния и не хранится в БД.
    Второй элемент — id отклика для шага `application_status`.
    """
    if user.role is None:
        return "role_selection", None

    if user.role == UserRole.CANDIDATE:
        has_profile = await CandidateProfile.filter(user_id=user.user_id).exists()
        if not has_profile:
            return "candidate_profile", None

        application = (
            await Application.filter(
                candidate_id=user.user_id, status__in=ACTIVE_APPLICATION_STATUSES
            )
            .order_by("-created_at")
            .first()
        )
        if application is not None:
            return "application_status", application.id
        return "feed", None

    has_vacancies = await Vacancy.filter(employer_id=user.user_id).exists()
    return ("employer_home" if has_vacancies else "vacancy_create"), None
