"""POST /api/vacancies/{id}/apply. Разделы 32, 57, 78, 79 тех-доки."""

import asyncio
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications import router as applications_router
from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import ApplicationStatus, UserRole, VacancyStatus
from app.core.rate_limit import SlidingWindowRateLimiter
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload

EMPLOYER_ID = 790000
_candidate_ids = count(790001)

FITTING_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": date(2026, 10, 1),
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Вакансии модуля не должны попадать в ленту соседних тестов."""
    yield
    await Vacancy.filter(employer_id=EMPLOYER_ID).delete()


async def _employer() -> User:
    employer = await User.get_or_none(user_id=EMPLOYER_ID)
    if employer is None:
        employer = await User.create(
            user_id=EMPLOYER_ID, first_name="Работодатель", role=UserRole.EMPLOYER
        )
    return employer


async def _vacancy(status: VacancyStatus = VacancyStatus.PUBLISHED) -> Vacancy:
    return await Vacancy.create(
        employer=await _employer(),
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=status,
    )


async def _candidate(
    client: AsyncClient, *, role: UserRole | None = UserRole.CANDIDATE
) -> User:
    user_id = next(_candidate_ids)
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    if role is not None:
        await User.filter(user_id=user_id).update(role=role)
    if role is UserRole.CANDIDATE:
        await CandidateProfile.create(user_id=user_id, **FITTING_PROFILE)
    return await User.get(user_id=user_id)


async def _apply(client: AsyncClient, vacancy: Vacancy):
    return await client.post(f"/api/vacancies/{vacancy.id}/apply")


# --- Доступ -----------------------------------------------------------------


async def test_apply_requires_session(client: AsyncClient) -> None:
    vacancy = await _vacancy()

    assert (await _apply(client, vacancy)).status_code == 401


async def test_apply_requires_candidate_role(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    await _candidate(client, role=UserRole.EMPLOYER)

    response = await _apply(client, vacancy)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_apply_requires_selected_role(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    await _candidate(client, role=None)

    response = await _apply(client, vacancy)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_selected"


# --- Состояние вакансии -----------------------------------------------------


async def test_apply_to_unknown_vacancy_returns_404(client: AsyncClient) -> None:
    await _candidate(client)

    response = await client.post("/api/vacancies/999999/apply")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_apply_to_draft_vacancy_is_refused(client: AsyncClient) -> None:
    vacancy = await _vacancy(VacancyStatus.DRAFT)
    await _candidate(client)

    response = await _apply(client, vacancy)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vacancy_not_published"
    assert await Application.filter(vacancy_id=vacancy.id).count() == 0


async def test_apply_to_closed_vacancy_is_refused(client: AsyncClient) -> None:
    """Раздел 57: на закрытую вакансию новые отклики запрещены."""
    vacancy = await _vacancy(VacancyStatus.CLOSED)
    await _candidate(client)

    response = await _apply(client, vacancy)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vacancy_not_published"


# --- Создание отклика -------------------------------------------------------


async def test_apply_creates_application_in_screening(client: AsyncClient) -> None:
    """Раздел 32: сразу после создания отклик идёт на первичный отбор."""
    vacancy = await _vacancy()
    candidate = await _candidate(client)

    response = await _apply(client, vacancy)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == ApplicationStatus.SCREENING.value

    application = await Application.get(id=body["id"])
    assert application.candidate_id == candidate.user_id
    assert application.status == ApplicationStatus.SCREENING


async def test_repeated_apply_returns_existing_application(
    client: AsyncClient,
) -> None:
    """Раздел 57: дубликат возвращает существующий отклик, а не ошибку."""
    vacancy = await _vacancy()
    await _candidate(client)
    first = await _apply(client, vacancy)

    repeated = await _apply(client, vacancy)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]
    assert await Application.filter(vacancy_id=vacancy.id).count() == 1


async def test_repeated_apply_does_not_reset_screening(client: AsyncClient) -> None:
    """Повтор не должен вернуть уже прошедший отбор обратно в `screening`."""
    vacancy = await _vacancy()
    await _candidate(client)
    application_id = (await _apply(client, vacancy)).json()["id"]
    passed = await client.post(
        f"/api/applications/{application_id}/screening", json={"answers": []}
    )
    assert passed.status_code == 200, passed.text

    repeated = await _apply(client, vacancy)

    assert repeated.status_code == 200
    assert repeated.json()["status"] == ApplicationStatus.PASSED.value
    application = await Application.get(id=application_id)
    assert application.status == ApplicationStatus.PASSED


async def test_concurrent_applies_create_one_application(
    client: AsyncClient,
) -> None:
    """Раздел 79: повтор запроса не создаёт дублирующую сущность."""
    vacancy = await _vacancy()
    await _candidate(client)

    responses = await asyncio.gather(*[_apply(client, vacancy) for _ in range(5)])

    assert {response.status_code for response in responses} <= {200, 201}
    assert len({response.json()["id"] for response in responses}) == 1
    assert await Application.filter(vacancy_id=vacancy.id).count() == 1


async def test_different_candidates_apply_independently(
    client: AsyncClient,
) -> None:
    vacancy = await _vacancy()
    await _candidate(client)
    first = await _apply(client, vacancy)
    await _candidate(client)
    second = await _apply(client, vacancy)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert await Application.filter(vacancy_id=vacancy.id).count() == 2


async def test_apply_removes_vacancy_from_feed(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    await _candidate(client)
    before = (await client.get("/api/vacancies/feed")).json()
    assert vacancy.id in {item["id"] for item in before["items"]}

    await _apply(client, vacancy)

    after = (await client.get("/api/vacancies/feed")).json()
    assert vacancy.id not in {item["id"] for item in after["items"]}


# --- Аналитика и защита -----------------------------------------------------


async def test_apply_writes_analytics_event(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    candidate = await _candidate(client)

    await _apply(client, vacancy)
    # Повтор события не дублирует: отклик уже существует
    await _apply(client, vacancy)

    events = await AnalyticsEvent.filter(
        user_id=candidate.user_id, event_name="application_created"
    )
    assert len(events) == 1
    assert events[0].payload["vacancy_id"] == vacancy.id


async def test_apply_rate_limit_returns_429(client: AsyncClient) -> None:
    """Раздел 78: отклик входит в список операций, которым нужна защита."""
    vacancy = await _vacancy()
    await _candidate(client)
    original = applications_router.apply_rate_limiter
    applications_router.apply_rate_limiter = SlidingWindowRateLimiter(
        limit=2, window_seconds=60
    )
    try:
        responses = [await _apply(client, vacancy) for _ in range(3)]
    finally:
        applications_router.apply_rate_limiter = original

    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "rate_limited"
