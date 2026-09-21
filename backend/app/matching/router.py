"""Лента вакансий.

Маршрут живёт в модуле matching, а не vacancies: подбор — зона backend
кандидата, а CRUD вакансий развивается отдельно.

Важно при добавлении `GET /vacancies/{id}`: этот роутер должен
подключаться раньше, иначе `feed` попадёт в параметр пути.
"""

from fastapi import APIRouter, Query

from app.auth.dependencies import CandidateUser
from app.matching import service
from app.matching.schemas import FeedResponse

router = APIRouter(prefix="/vacancies", tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    user: CandidateUser,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> FeedResponse:
    """Подходящие кандидату опубликованные вакансии."""
    return await service.get_feed(user, limit=limit, offset=offset)
