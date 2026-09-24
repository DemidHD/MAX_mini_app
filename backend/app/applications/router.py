"""Эндпоинты отклика. Разделы 27, 32, 33, 34, 35 тех-доки.

Три роутера: отклик на вакансию живёт под `/vacancies`, работа кандидата с
откликом — под `/applications`, работа работодателя — под `/employer`; так их
разделяет раздел 27.
"""

from fastapi import APIRouter, Query, Response, status

from app.applications import employer_service, service
from app.applications.schemas import (
    ApplicationCreatedResponse,
    CandidateApplicationRead,
    CandidateListResponse,
    DecisionRequest,
    DecisionResponse,
    ScreeningResultResponse,
    ScreeningStateResponse,
    ScreeningSubmitRequest,
)
from app.auth.dependencies import CandidateUser, EmployerUser
from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter

router = APIRouter(prefix="/applications", tags=["applications"])
employer_router = APIRouter(prefix="/employer", tags=["employer"])
vacancies_router = APIRouter(prefix="/vacancies", tags=["applications"])

apply_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.apply_rate_limit_requests,
    window_seconds=settings.apply_rate_limit_window_seconds,
)


@vacancies_router.post(
    "/{vacancy_id}/apply",
    response_model=ApplicationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply(
    vacancy_id: int, user: CandidateUser, response: Response
) -> ApplicationCreatedResponse:
    """Создаёт отклик на вакансию и отправляет его на первичный отбор.

    Повторный запрос отклик не дублирует: возвращается существующий, но с
    кодом `200` вместо `201`.
    """
    await apply_rate_limiter.check(str(user.user_id))
    application, created = await service.apply(user, vacancy_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return ApplicationCreatedResponse(
        id=application.id,
        vacancy_id=application.vacancy_id,
        status=application.status,
        created_at=application.created_at,
    )


@router.get("/{application_id}", response_model=CandidateApplicationRead)
async def get_application(
    application_id: int, user: CandidateUser
) -> CandidateApplicationRead:
    """Статус отклика кандидата — переживает перезагрузку экрана (C06/C07)."""
    return await service.get_application(user, application_id)


@router.get("/{application_id}/screening", response_model=ScreeningStateResponse)
async def get_screening(
    application_id: int, user: CandidateUser
) -> ScreeningStateResponse:
    """Вопросы отбора и сохранённые ответы по отклику кандидата."""
    return await service.get_screening(user, application_id)


@router.post("/{application_id}/screening", response_model=ScreeningResultResponse)
async def submit_screening(
    application_id: int, payload: ScreeningSubmitRequest, user: CandidateUser
) -> ScreeningResultResponse:
    """Проходит первичный отбор и выставляет результат hard filters."""
    return await service.submit_screening(user, application_id, payload)


@router.post("/{application_id}/decision", response_model=DecisionResponse)
async def decide(
    application_id: int, payload: DecisionRequest, user: EmployerUser
) -> DecisionResponse:
    """Решение работодателя по отклику: отклонить или пригласить."""
    return await employer_service.decide(user, application_id, payload)


@employer_router.get(
    "/vacancies/{vacancy_id}/candidates", response_model=CandidateListResponse
)
async def list_candidates(
    vacancy_id: int,
    user: EmployerUser,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> CandidateListResponse:
    """Кандидаты вакансии, прошедшие первичный отбор."""
    return await employer_service.list_candidates(
        user, vacancy_id, limit=limit, offset=offset
    )
