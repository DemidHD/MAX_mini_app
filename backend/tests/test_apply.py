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


async def test_apply_guards_and_vacancy_state(client: AsyncClient) -> None:
    # 1. Без сессии — 401
    session_vacancy = await _vacancy()
    assert (await _apply(client, session_vacancy)).status_code == 401

    # 2. Не той роли и без выбранной роли — 403 с разными кодами
    await _candidate(client, role=UserRole.EMPLOYER)
    wrong_role = await _apply(client, session_vacancy)
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    await _candidate(client, role=None)
    no_role = await _apply(client, session_vacancy)
    assert no_role.status_code == 403
    assert no_role.json()["error"]["code"] == "role_not_selected"

    # 3. Несуществующая вакансия — 404
    await _candidate(client)
    unknown = await client.post("/api/vacancies/999999/apply")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "vacancy_not_found"

    # 4. Черновик и закрытая вакансия откликов не принимают (раздел 57)
    draft_vacancy = await _vacancy(VacancyStatus.DRAFT)
    draft_response = await _apply(client, draft_vacancy)
    assert draft_response.status_code == 409
    assert draft_response.json()["error"]["code"] == "vacancy_not_published"
    assert await Application.filter(vacancy_id=draft_vacancy.id).count() == 0

    closed_vacancy = await _vacancy(VacancyStatus.CLOSED)
    closed_response = await _apply(client, closed_vacancy)
    assert closed_response.status_code == 409
    assert closed_response.json()["error"]["code"] == "vacancy_not_published"


# --- Создание отклика, идемпотентность, побочные эффекты --------------------


async def test_apply_happy_path_and_idempotency(client: AsyncClient) -> None:
    # 1. Отклик сразу уходит на первичный отбор (раздел 32)
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    created = await _apply(client, vacancy)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == ApplicationStatus.SCREENING.value
    application = await Application.get(id=body["id"])
    assert application.candidate_id == candidate.user_id
    assert application.status == ApplicationStatus.SCREENING

    # 2. Повторный отклик возвращает существующий, а не ошибку (раздел 57)
    repeated = await _apply(client, vacancy)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == body["id"]
    assert await Application.filter(vacancy_id=vacancy.id).count() == 1

    # 3. Пройденный отбор повтором отклика не откатывается обратно в screening
    passed = await client.post(
        f"/api/applications/{body['id']}/screening", json={"answers": []}
    )
    assert passed.status_code == 200, passed.text
    after_screening = await _apply(client, vacancy)
    assert after_screening.status_code == 200
    assert after_screening.json()["status"] == ApplicationStatus.PASSED.value
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.PASSED

    # 4. Разные кандидаты откликаются на одну вакансию независимо друг от друга
    await _candidate(client)
    other = await _apply(client, vacancy)
    assert other.status_code == 201
    assert other.json()["id"] != body["id"]
    assert await Application.filter(vacancy_id=vacancy.id).count() == 2

    # 5. Отклик убирает вакансию из ленты откликнувшегося
    feed_vacancy = await _vacancy()
    await _candidate(client)
    before_feed = (await client.get("/api/vacancies/feed")).json()
    assert feed_vacancy.id in {item["id"] for item in before_feed["items"]}
    await _apply(client, feed_vacancy)
    after_feed = (await client.get("/api/vacancies/feed")).json()
    assert feed_vacancy.id not in {item["id"] for item in after_feed["items"]}

    # 6. Аналитика пишет событие один раз, даже если отклик повторён
    analytics_vacancy = await _vacancy()
    analytics_candidate = await _candidate(client)
    await _apply(client, analytics_vacancy)
    await _apply(client, analytics_vacancy)
    events = await AnalyticsEvent.filter(
        user_id=analytics_candidate.user_id, event_name="application_created"
    )
    assert len(events) == 1
    assert events[0].payload["vacancy_id"] == analytics_vacancy.id


# --- Конкурентность и rate limit (диагностика важнее компактности) ------------


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
