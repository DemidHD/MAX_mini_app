"""Эндпоинты слотов и бронирования. Разделы 27, 37, 78 тех-доки.

Два роутера: слоты живут под `/vacancies`, бронирование — под `/matches`,
как их разделяет раздел 27.
"""

from fastapi import APIRouter, Response, status

from app.auth.dependencies import CandidateUser, CurrentUser, EmployerUser
from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.interviews import service
from app.interviews.schemas import (
    BookingRequest,
    InterviewRead,
    InterviewSlotRead,
    SlotCreateRequest,
    SlotListResponse,
)

router = APIRouter(prefix="/matches", tags=["interviews"])
vacancies_router = APIRouter(prefix="/vacancies", tags=["interviews"])

book_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.book_rate_limit_requests,
    window_seconds=settings.book_rate_limit_window_seconds,
)


@vacancies_router.post(
    "/{vacancy_id}/slots",
    response_model=InterviewSlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_slot(
    vacancy_id: int, payload: SlotCreateRequest, user: EmployerUser
) -> InterviewSlotRead:
    """Добавляет время собеседования по вакансии работодателя."""
    return await service.create_slot(user, vacancy_id, payload)


@vacancies_router.get("/{vacancy_id}/slots", response_model=SlotListResponse)
async def list_slots(vacancy_id: int, user: CurrentUser) -> SlotListResponse:
    """Слоты вакансии: работодателю — свои, кандидату — доступные к выбору.

    Роль здесь не фиксируется зависимостью: раздел 37 описывает один
    эндпоинт на обе стороны, а состав ответа определяет сервис.
    """
    return await service.list_slots(user, vacancy_id)


@vacancies_router.delete(
    "/{vacancy_id}/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def cancel_slot(vacancy_id: int, slot_id: int, user: EmployerUser) -> Response:
    """Снимает ранее созданное время. Забронированный слот не отменяется."""
    await service.cancel_slot(user, vacancy_id, slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{match_id}/book",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def book(
    match_id: int, payload: BookingRequest, user: CandidateUser, response: Response
) -> InterviewRead:
    """Бронирует слот и назначает собеседование.

    Повторный запрос с тем же слотом собеседование не дублирует: возвращается
    существующее, но с кодом `200` вместо `201`.
    """
    await book_rate_limiter.check(str(user.user_id))
    interview, created = await service.book(user, match_id, payload)
    if not created:
        response.status_code = status.HTTP_200_OK
    return interview
