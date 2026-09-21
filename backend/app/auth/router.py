"""HTTP-транспорт авторизации. Бизнес-логика живёт в service.py (раздел 74)."""

from fastapi import APIRouter, Response

from app.auth import service
from app.auth.models import Session
from app.auth.schemas import AuthMaxRequest, AuthMaxResponse
from app.core.config import settings
from app.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/max", response_model=AuthMaxResponse)
async def auth_max(payload: AuthMaxRequest, response: Response) -> AuthMaxResponse:
    """Проверяет initData, заводит сессию и отдаёт текущий шаг сценария."""
    user, session = await service.authenticate(payload.init_data)
    _set_session_cookie(response, session)

    current_step, application_id = await service.compute_current_step(user)
    return AuthMaxResponse(
        user=UserRead.from_user(user),
        current_step=current_step,
        application_id=application_id,
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
