"""Эндпоинт справочника навыков. Не из тех-доки."""

from fastapi import APIRouter, Query

from app.auth.dependencies import CurrentUser
from app.skills import service
from app.skills.schemas import SkillListResponse

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillListResponse)
async def list_skills(
    _: CurrentUser,
    query: str | None = Query(default=None, max_length=100),
) -> SkillListResponse:
    """Справочник навыков — источник значений и для ручного выбора кандидатом,
    и для отображения работодателю (единый список без дублей вроде
    «Excel»/«MS Excel»). Доступен любому авторизованному пользователю —
    справочник не содержит персональных данных.
    """
    return await service.list_skills(query)
