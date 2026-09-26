"""Авторизация через MAX и серверные сессии. Разделы 6, 7, 10 тех-доки."""

import asyncio
import logging
import time
from datetime import timedelta
from uuid import UUID

from app.applications.models import Application
from app.auth.init_data import InitData, MaxUser, validate_init_data
from app.auth.models import Session
from app.candidates.models import CandidateProfile
from app.core import cache
from app.core.config import settings
from app.core.database import utcnow
from app.core.enums import ApplicationStatus, UserRole
from app.users.models import User
from app.vacancies.models import Vacancy

logger = logging.getLogger("app.auth")

# Раздел 10: сессия проверяется на каждый запрос — это самый частый путь в
# приложении. Кэшируется только неизменная часть — `session_id -> user_id`
# (какая роль, имя и т.д. у пользователя, кэш не хранит вовсе): эта связка не
# меняется, пока сессия жива, и специально не требует инвалидации при смене
# роли/профиля/аватарки. `User` на кэш-попадании всё равно читается заново из
# БД — иначе объект пришлось бы собирать вручную мимо ORM, а весь остальной
# код (например `users.service.update_profile`) вызывает `user.save(...)`
# прямо на переданном объекте и должен получать настоящий, а не восстановленный
# из JSON экземпляр.
_SESSION_CACHE_PREFIX = "cache:session:"

_session_cleanup_lock = asyncio.Lock()
_last_session_cleanup: float | None = None

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
    await _cleanup_expired_sessions_if_due()
    user = await _upsert_user(init_data.user)
    session = await Session.create(
        user=user,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    return user, session


async def cleanup_expired_sessions(*, force: bool = False) -> int:
    """Периодически удаляет сессии, которые больше не предъявляются клиентами."""
    global _last_session_cleanup

    now = time.monotonic()
    interval = settings.session_cleanup_interval_seconds
    if (
        not force
        and _last_session_cleanup is not None
        and now - _last_session_cleanup < interval
    ):
        return 0

    async with _session_cleanup_lock:
        now = time.monotonic()
        if (
            not force
            and _last_session_cleanup is not None
            and now - _last_session_cleanup < interval
        ):
            return 0
        # Даже неуспешную попытку ограничиваем интервалом, чтобы сбой БД не
        # создавал лавину одинаковых cleanup-запросов на каждой авторизации.
        _last_session_cleanup = now
        return await Session.filter(expires_at__lte=utcnow()).delete()


async def _cleanup_expired_sessions_if_due() -> None:
    try:
        await cleanup_expired_sessions()
    except Exception:
        # Сервисная очистка не должна превращать валидную авторизацию в 500.
        logger.exception("Не удалось очистить просроченные сессии")


async def _upsert_user(max_user: MaxUser) -> User:
    """Создаёт пользователя при первом входе, иначе обновляет актуальные данные.

    Имя и фамилия при повторном входе не перезаписываются: пользователь мог
    изменить их внутри MAX Найм (раздел 7).
    """
    user, created = await User.get_or_create(
        user_id=max_user.user_id,
        defaults={
            "first_name": max_user.first_name,
            "last_name": max_user.last_name,
            "username": max_user.username,
            "language_code": max_user.language_code,
        },
    )
    if created:
        return user

    user.username = max_user.username
    user.language_code = max_user.language_code
    user.last_auth_at = utcnow()
    await user.save(update_fields=["username", "language_code", "last_auth_at", "updated_at"])
    return user


async def get_session_user(raw_session_id: str) -> User | None:
    """Возвращает пользователя действующей сессии; просроченную сессию удаляет.

    На кэш-попадании пропускает обращение к `sessions` целиком — саму
    таблицу сессий и, главное, запись `last_used_at` при каждом запросе:
    это поле нигде не используется бизнес-логикой (`cleanup_expired_sessions`
    чистит по `expires_at`), только для диагностики, поэтому отставание на
    TTL кэша ничем не рискует. Есть и обратная сторона: если сессия истекает
    прямо внутри окна TTL, кэш может ещё TTL секунд считать её действующей —
    цена этого при `SESSION_TTL_HOURS` в днях/неделях против частоты запроса
    на каждый эндпоинт признана приемлемой.
    """
    try:
        session_id = UUID(raw_session_id)
    except ValueError:
        return None

    cache_key = f"{_SESSION_CACHE_PREFIX}{session_id}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        user = await User.get_or_none(user_id=cached["user_id"])
        if user is not None:
            return user
        # Не должно происходить (пользователи не удаляются), но кэш на
        # исчезнувшего пользователя лучше забыть и пойти обычным путём.
        await cache.delete(cache_key)

    session = await Session.get_or_none(id=session_id).select_related("user")
    if session is None:
        return None

    if session.is_expired():
        await session.delete()
        return None

    session.last_used_at = utcnow()
    await session.save(update_fields=["last_used_at"])
    await cache.set_json(
        cache_key, {"user_id": session.user_id}, settings.cache_session_ttl_seconds
    )
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
