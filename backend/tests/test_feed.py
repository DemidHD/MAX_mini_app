"""GET /api/vacancies/feed. Раздел 30 тех-доки."""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient

from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import ApplicationStatus, CriterionType, UserRole, VacancyStatus
from app.users.models import User
from app.vacancies.models import Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

EMPLOYER_ID = 740000


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Лента показывает все опубликованные вакансии, поэтому база общая
    между тестами мешает: чистим перед каждым."""
    await Vacancy.all().delete()
    yield


async def _employer() -> User:
    employer = await User.get_or_none(user_id=EMPLOYER_ID)
    if employer is None:
        employer = await User.create(
            user_id=EMPLOYER_ID, first_name="Работодатель", role=UserRole.EMPLOYER
        )
    return employer


async def _vacancy(
    title: str,
    *,
    status: VacancyStatus = VacancyStatus.PUBLISHED,
    criteria: list[tuple[CriterionType, dict, bool]] | None = None,
    salary_max: Decimal | None = Decimal("90000"),
) -> Vacancy:
    vacancy = await Vacancy.create(
        employer=await _employer(),
        title=title,
        location="Москва",
        salary_max=salary_max,
        schedule="full_time",
        status=status,
    )
    for criterion_type, value, required in criteria or []:
        await VacancyCriterion.create(
            vacancy=vacancy, type=criterion_type, required=required, value=value
        )
    return vacancy


async def _login_candidate(
    client: AsyncClient, user_id: int, *, with_profile: bool = True, **profile_kwargs
) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200
    await User.filter(user_id=user_id).update(role=UserRole.CANDIDATE)

    if with_profile:
        defaults = {
            "desired_role": "Бариста",
            "city": "Москва",
            "salary": Decimal("70000"),
            "schedule": "full_time",
            "experience_months": 24,
            "available_from": date(2026, 10, 1),
        }
        await CandidateProfile.create(user_id=user_id, **(defaults | profile_kwargs))
    return await User.get(user_id=user_id)


async def _feed(client: AsyncClient, **params) -> dict:
    response = await client.get("/api/vacancies/feed", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _titles(body: dict) -> list[str]:
    return [item["title"] for item in body["items"]]


async def test_feed_requires_candidate_role(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=741001))},
    )

    without_role = await client.get("/api/vacancies/feed")
    assert without_role.status_code == 403
    assert without_role.json()["error"]["code"] == "role_not_selected"

    await User.filter(user_id=741001).update(role=UserRole.EMPLOYER)
    as_employer = await client.get("/api/vacancies/feed")
    assert as_employer.status_code == 403
    assert as_employer.json()["error"]["code"] == "wrong_role"


async def test_feed_requires_session(client: AsyncClient) -> None:
    response = await client.get("/api/vacancies/feed")

    assert response.status_code == 401


async def test_only_published_vacancies_are_shown(client: AsyncClient) -> None:
    await _login_candidate(client, 741002)
    await _vacancy("Опубликованная")
    await _vacancy("Черновик", status=VacancyStatus.DRAFT)
    await _vacancy("Закрытая", status=VacancyStatus.CLOSED)

    body = await _feed(client)

    assert _titles(body) == ["Опубликованная"]


async def test_vacancy_without_criteria_is_shown(client: AsyncClient) -> None:
    await _login_candidate(client, 741003)
    await _vacancy("Без условий")

    assert "Без условий" in _titles(await _feed(client))


async def test_vacancy_with_failing_required_criterion_is_hidden(
    client: AsyncClient,
) -> None:
    await _login_candidate(client, 741004, city="Москва")
    await _vacancy(
        "Казань обязательна",
        criteria=[(CriterionType.LOCATION, {"city": "Казань"}, True)],
    )
    await _vacancy(
        "Москва подходит",
        criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)],
    )

    assert _titles(await _feed(client)) == ["Москва подходит"]


async def test_failing_optional_criterion_does_not_hide_vacancy(
    client: AsyncClient,
) -> None:
    await _login_candidate(client, 741005, city="Москва")
    await _vacancy(
        "Желательно Казань",
        criteria=[(CriterionType.LOCATION, {"city": "Казань"}, False)],
    )

    assert _titles(await _feed(client)) == ["Желательно Казань"]


async def test_uncheckable_criterion_keeps_vacancy(client: AsyncClient) -> None:
    """Нет данных в профиле — не повод прятать вакансию."""
    await _login_candidate(client, 741006, city=None)
    await _vacancy(
        "Нужна Москва", criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)]
    )

    assert _titles(await _feed(client)) == ["Нужна Москва"]


async def test_salary_expectations_filter_vacancy_out(client: AsyncClient) -> None:
    await _login_candidate(client, 741007, salary=Decimal("120000"))
    await _vacancy(
        "Потолок ниже ожиданий",
        criteria=[(CriterionType.SALARY, {"max": 80000}, True)],
    )

    assert _titles(await _feed(client)) == []


async def test_experience_and_date_are_applied(client: AsyncClient) -> None:
    await _login_candidate(
        client, 741008, experience_months=6, available_from=date(2026, 12, 1)
    )
    await _vacancy(
        "Нужен опыт от 2 лет",
        criteria=[(CriterionType.EXPERIENCE, {"min_months": 24}, True)],
    )
    await _vacancy(
        "Выход до октября",
        criteria=[(CriterionType.AVAILABLE_FROM, {"date": "2026-10-01"}, True)],
    )
    await _vacancy(
        "Опыта хватает",
        criteria=[(CriterionType.EXPERIENCE, {"min_months": 3}, True)],
    )

    assert _titles(await _feed(client)) == ["Опыта хватает"]


async def test_already_applied_vacancy_leaves_feed(client: AsyncClient) -> None:
    candidate = await _login_candidate(client, 741009)
    applied = await _vacancy("Уже откликнулся")
    await _vacancy("Новая")
    await Application.create(
        vacancy=applied, candidate=candidate, status=ApplicationStatus.SCREENING
    )

    assert _titles(await _feed(client)) == ["Новая"]


async def test_feed_is_empty_without_profile(client: AsyncClient) -> None:
    await _login_candidate(client, 741010, with_profile=False)
    await _vacancy("Есть вакансия")

    body = await _feed(client)

    assert body["items"] == []
    assert body["total"] == 0


async def test_card_contains_vacancy_conditions(client: AsyncClient) -> None:
    await _login_candidate(client, 741011)
    await _vacancy(
        "С условиями",
        criteria=[(CriterionType.SCHEDULE, {"schedule": "full_time"}, True)],
    )

    card = (await _feed(client))["items"][0]

    assert card["location"] == "Москва"
    assert card["salary_max"] == "90000.00"
    assert card["criteria"] == [
        {"type": "schedule", "required": True, "value": {"schedule": "full_time"}}
    ]


async def test_pagination(client: AsyncClient) -> None:
    await _login_candidate(client, 741012)
    for index in range(3):
        await _vacancy(f"Вакансия {index}")

    first = await _feed(client, limit=2)
    second = await _feed(client, limit=2, offset=2)

    assert len(first["items"]) == 2
    assert first["total"] >= 3
    assert len(second["items"]) >= 1
    assert set(_titles(first)).isdisjoint(_titles(second))


async def test_invalid_pagination_is_rejected(client: AsyncClient) -> None:
    await _login_candidate(client, 741013)

    response = await client.get("/api/vacancies/feed", params={"limit": 500})

    assert response.status_code == 422
