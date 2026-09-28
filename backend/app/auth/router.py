"""HTTP-транспорт авторизации. Бизнес-логика живёт в service.py (раздел 74)."""

from fastapi import APIRouter, Request, Response, status

from app.auth import service
from app.auth.dependencies import CurrentUser, get_raw_session_id
from app.auth.models import Session
from app.auth.schemas import AuthMaxRequest, AuthMaxResponse
from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
auth_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.auth_rate_limit_requests,
    window_seconds=settings.auth_rate_limit_window_seconds,
)


@router.post("/max", response_model=AuthMaxResponse)
async def auth_max(
    payload: AuthMaxRequest, request: Request, response: Response
) -> AuthMaxResponse:
    """Проверяет initData, заводит сессию и отдаёт текущий шаг сценария."""
    client_host = request.client.host if request.client else "unknown"
    await auth_rate_limiter.check(client_host)
    user, session = await service.authenticate(payload.init_data)
    _set_session_cookie(response, session)

    current_step, application_id = await service.compute_current_step(user)
    return AuthMaxResponse(
        user=UserRead.from_user(user),
        current_step=current_step,
        application_id=application_id,
        session_token=str(session.id),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: CurrentUser, request: Request, response: Response
) -> None:
    """Отзывает текущую сессию (раздел 10) и сбрасывает cookie.

    Как и остальные защищённые эндпоинты, требует действующую сессию —
    без неё `CurrentUser` уже вернёт 401 (раздел 10 тех-доки, cookie ИЛИ
    заголовок `Authorization: Bearer …`).
    """
    del user
    raw_session_id = get_raw_session_id(request)
    if raw_session_id:
        await service.logout(raw_session_id)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.is_production,
        samesite="none" if settings.is_production else "lax",
    )


def _set_session_cookie(response: Response, session: Session) -> None:
    """HTTP-only cookie сессии (раздел 10).

    Mini App работает во встроенном браузере на стороннем домене, поэтому в
    production нужен SameSite=None, а он требует Secure. Локально по http
    такая пара не сохранится браузером, поэтому там SameSite=Lax.
    """
    response.set_cookie(
        key=settings.session_cookie_name,
        value=str(session.id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="none" if settings.is_production else "lax",
        path="/",
    )
