"""Зависимости авторизации. Раздел 11 тех-доки.

Текущий пользователь берётся только из серверной сессии. Идентификаторы,
присланные frontend в теле запроса, источником истины не являются.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.auth.service import get_session_user
from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import bind_user_id
from app.users.models import User


def get_raw_session_id(request: Request) -> str | None:
    """Id сессии из cookie ИЛИ заголовка `Authorization: Bearer …`.

    Заголовок нужен web.max.ru: там Mini App открыт во фрейме на стороннем
    домене, и браузер блокирует cookie как стороннюю (раздел 10 тех-доки).
    """
    raw_session_id = request.cookies.get(settings.session_cookie_name)
    if not raw_session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_session_id = auth_header.removeprefix("Bearer ").strip()
    return raw_session_id or None


async def require_auth(request: Request) -> User:
    """Текущий пользователь или 401."""
    raw_session_id = get_raw_session_id(request)
    if not raw_session_id:
        raise UnauthorizedError("Сессия не найдена")

    user = await get_session_user(raw_session_id)
    if user is None:
        raise UnauthorizedError("Сессия недействительна или истекла")

    bind_user_id(request, user.user_id)
    return user


CurrentUser = Annotated[User, Depends(require_auth)]


async def require_role(user: CurrentUser, role: UserRole) -> User:
    if user.role is None:
        # До выбора роли доступны только onboarding-эндпоинты (раздел 12)
        raise ForbiddenError("Сначала нужно выбрать роль", code="role_not_selected")
    if user.role != role:
        raise ForbiddenError("Действие доступно другой роли", code="wrong_role")
    return user


async def require_candidate(user: CurrentUser) -> User:
    return await require_role(user, UserRole.CANDIDATE)


async def require_employer(user: CurrentUser) -> User:
    return await require_role(user, UserRole.EMPLOYER)


async def require_any_role(user: CurrentUser) -> User:
    """Кандидат или работодатель — не важно, какая именно, только не гость
    без роли. Для действий, доступных обеим ролям одинаково (например R01)."""
    if user.role is None:
        raise ForbiddenError("Сначала нужно выбрать роль", code="role_not_selected")
    return user


CandidateUser = Annotated[User, Depends(require_candidate)]
EmployerUser = Annotated[User, Depends(require_employer)]
AnyRoleUser = Annotated[User, Depends(require_any_role)]
