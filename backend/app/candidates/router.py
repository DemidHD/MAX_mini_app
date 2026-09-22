"""Эндпоинты профиля кандидата. Раздел 27 тех-доки."""

from fastapi import APIRouter

from app.auth.dependencies import CandidateUser
from app.candidates import service
from app.candidates.schemas import CandidateProfileRead, CandidateProfileUpdateRequest

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.get("/profile", response_model=CandidateProfileRead)
async def get_profile(user: CandidateUser) -> CandidateProfileRead:
    """Профиль текущего кандидата. Если профиля ещё нет — 404."""
    return CandidateProfileRead.from_profile(await service.get_profile(user))


@router.patch("/profile", response_model=CandidateProfileRead)
async def update_profile(
    payload: CandidateProfileUpdateRequest, user: CandidateUser
) -> CandidateProfileRead:
    """Создаёт профиль при первом обращении, затем меняет переданные поля."""
    return CandidateProfileRead.from_profile(await service.save_profile(user, payload))
