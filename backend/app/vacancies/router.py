"""Эндпоинты вакансии. Разделы 27, 28, 29 тех-доки.

Два роутера: вакансия живёт под `/vacancies`, список кабинета работодателя —
под `/employer`, как их разделяет раздел 27.

Важно: этот роутер подключается после ленты, иначе `/vacancies/feed` попадёт
в `GET /vacancies/{vacancy_id}` как параметр пути.
"""

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.auth.dependencies import CurrentUser, EmployerUser
from app.vacancies import service
from app.vacancies.schemas import (
    VacancyCreateRequest,
    VacancyListResponse,
    VacancyRead,
    VacancyUpdateRequest,
)

router = APIRouter(prefix="/vacancies", tags=["vacancies"])
employer_router = APIRouter(prefix="/employer", tags=["vacancies"])


@router.post("", response_model=VacancyRead, status_code=status.HTTP_201_CREATED)
async def create_vacancy(
    payload: VacancyCreateRequest, user: EmployerUser, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Создаёт вакансию вместе с условиями и вопросами отбора."""
    return await service.create_vacancy(user, payload, background_tasks)


@router.get("/public/{token}", response_model=VacancyRead)
async def get_vacancy_by_public_token(
    token: str, user: CurrentUser, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Вакансия по публичной ссылке `{APP_URL}/v/{token}` (раздел 15).

    Два сегмента пути (`public/{token}`) не пересекаются с `{vacancy_id}`
    выше — коллизии, из-за которой роутер ленты подключается отдельно, здесь
    нет.
    """
    return await service.get_vacancy_by_public_token(user, token, background_tasks)


@router.get("/{vacancy_id}", response_model=VacancyRead)
async def get_vacancy(
    vacancy_id: int, user: CurrentUser, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Вакансия: работодателю — своя в любом статусе, кандидату — опубликованная."""
    return await service.get_vacancy(user, vacancy_id, background_tasks)


@router.patch("/{vacancy_id}", response_model=VacancyRead)
async def update_vacancy(
    vacancy_id: int, payload: VacancyUpdateRequest, user: EmployerUser
) -> VacancyRead:
    """Меняет вакансию. Публикация и закрытие — через поле `status`."""
    return await service.update_vacancy(user, vacancy_id, payload)


@router.delete("/{vacancy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vacancy(vacancy_id: int, user: EmployerUser) -> None:
    """Удаляет черновик вакансии. Эндпоинта нет в разделе 27 тех-доки —
    добавлен по тому же правилу, что запрещает `published → draft`: убрать
    можно только то, по чему точно не могло быть откликов."""
    await service.delete_vacancy(user, vacancy_id)


@employer_router.get("/vacancies", response_model=VacancyListResponse)
async def list_own_vacancies(
    user: EmployerUser,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> VacancyListResponse:
    """Вакансии текущего работодателя для его кабинета."""
    return await service.list_own_vacancies(user, limit=limit, offset=offset)
