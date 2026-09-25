"""Приём аналитических событий с фронта. Раздел 60 тех-доки, функция 33 UX-карты.

Часть каталога раздела 60 — чисто фронтовые события: за ними не стоит ни один
backend-эндпоинт, поэтому записать их раньше было некому (`просмотр
вакансии», «свайп», «просмотр карточки кандидата», «открытие доски статусов»,
«начало создания вакансии»). Остальные события каталога backend уже пишет
сам, из соответствующих операций (см. `app.analytics.service.log_event` по
всему коду) — им этот эндпоинт не нужен.

Белый список (`AnalyticsEventName`, `app.analytics.schemas`) — чтобы в
журнал не летело что попало: `event_name` вне списка отклоняется `422`
схемой, а не сохраняется как есть.
"""

from fastapi import APIRouter

from app.analytics import service as analytics
from app.analytics.schemas import AnalyticsEventRequest
from app.auth.dependencies import CurrentUser
from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter

router = APIRouter(prefix="/analytics", tags=["analytics"])

event_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.analytics_event_rate_limit_requests,
    window_seconds=settings.analytics_event_rate_limit_window_seconds,
)


@router.post("/events", status_code=204)
async def create_event(payload: AnalyticsEventRequest, user: CurrentUser) -> None:
    await event_rate_limiter.check(str(user.user_id))
    await analytics.log_event(
        payload.event_name, user_id=user.user_id, payload=payload.payload
    )
