"""GET/PATCH /api/candidate/profile. Разделы 14, 27 тех-доки."""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient

from app.applications.models import Application, ScreeningAnswer
from app.candidates.models import CandidateProfile
from app.core.enums import (
    ApplicationStatus,
    CriterionType,
    ScreeningQuestionType,
    UserRole,
    VacancyStatus,
)
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

EMPLOYER_ID = 750000

FULL_PROFILE = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": "70000.00",
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": "2026-10-01",
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Вакансии этого модуля не должны попадать в ленту соседних тестов."""
    yield
    await Vacancy.filter(employer_id=EMPLOYER_ID).delete()


async def _employer() -> User:
    employer = await User.get_or_none(user_id=EMPLOYER_ID)
    if employer is None:
        employer = await User.create(
            user_id=EMPLOYER_ID, first_name="Работодатель", role=UserRole.EMPLOYER
        )
    return employer


async def _login(client: AsyncClient, user_id: int, role: UserRole | None) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    if role is not None:
        await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _patch(client: AsyncClient, payload: dict) -> dict:
    response = await client.patch("/api/candidate/profile", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_profile_requires_session(client: AsyncClient) -> None:
    assert (await client.get("/api/candidate/profile")).status_code == 401
    assert (
        await client.patch("/api/candidate/profile", json={"city": "Москва"})
    ).status_code == 401


async def test_profile_requires_candidate_role(client: AsyncClient) -> None:
    await _login(client, 750001, None)

    without_role = await client.get("/api/candidate/profile")
    assert without_role.status_code == 403
    assert without_role.json()["error"]["code"] == "role_not_selected"

    await User.filter(user_id=750001).update(role=UserRole.EMPLOYER)
    as_employer = await client.patch(
        "/api/candidate/profile", json={"desired_role": "Бариста"}
    )
    assert as_employer.status_code == 403
    assert as_employer.json()["error"]["code"] == "wrong_role"
    assert await CandidateProfile.get_or_none(user_id=750001) is None


async def test_get_before_creation_returns_404(client: AsyncClient) -> None:
    await _login(client, 750002, UserRole.CANDIDATE)

    response = await client.get("/api/candidate/profile")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "candidate_profile_not_found"


async def test_patch_creates_profile(client: AsyncClient) -> None:
    await _login(client, 750003, UserRole.CANDIDATE)

    created = await _patch(client, FULL_PROFILE)

    assert created["user_id"] == 750003
    assert created["desired_role"] == "Бариста"
    assert created["salary"] == "70000.00"
    assert created["experience_months"] == 24
    assert created["available_from"] == "2026-10-01"

    stored = await CandidateProfile.get(user_id=750003)
    assert stored.city == "Москва"
    assert stored.schedule == "full_time"
    assert stored.available_from == date(2026, 10, 1)
    assert (await client.get("/api/candidate/profile")).json() == created


async def test_creation_requires_desired_role(client: AsyncClient) -> None:
    await _login(client, 750004, UserRole.CANDIDATE)

    response = await client.patch("/api/candidate/profile", json={"city": "Москва"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "desired_role_required"
    assert await CandidateProfile.get_or_none(user_id=750004) is None


async def test_partial_update_keeps_other_fields(client: AsyncClient) -> None:
    await _login(client, 750005, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)

    updated = await _patch(client, {"salary": "85000"})

    assert updated["salary"] == "85000.00"
    assert updated["desired_role"] == "Бариста"
    assert updated["city"] == "Москва"
    assert updated["experience_months"] == 24
    assert updated["updated_at"] >= updated["created_at"]


async def test_null_clears_optional_field(client: AsyncClient) -> None:
    await _login(client, 750006, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)

    updated = await _patch(client, {"city": None, "available_from": None})

    assert updated["city"] is None
    assert updated["available_from"] is None
    assert updated["schedule"] == "full_time"


async def test_empty_strings_are_normalized(client: AsyncClient) -> None:
    """Пустой город — очистка поля, пустая желаемая должность — ошибка."""
    await _login(client, 750007, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)

    cleared = await _patch(client, {"city": "   "})
    assert cleared["city"] is None

    response = await client.patch("/api/candidate/profile", json={"desired_role": " "})
    assert response.status_code == 422
    assert (await CandidateProfile.get(user_id=750007)).desired_role == "Бариста"


async def test_invalid_values_are_rejected(client: AsyncClient) -> None:
    await _login(client, 750008, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)

    invalid_payloads = [
        {"salary": "-1"},
        {"salary": "12345678901234"},
        {"salary": "100.123"},
        {"experience_months": -1},
        {"experience_months": 5000},
        {"desired_role": "Б" * 256},
        {"city": "М" * 256},
        {"schedule": "ф" * 101},
        {"available_from": "не дата"},
    ]
    for payload in invalid_payloads:
        response = await client.patch("/api/candidate/profile", json=payload)
        assert response.status_code == 422, (payload, response.text)

    stored = await CandidateProfile.get(user_id=750008)
    assert stored.salary == Decimal("70000.00")
    assert stored.experience_months == 24


async def test_empty_patch_does_not_change_profile(client: AsyncClient) -> None:
    await _login(client, 750009, UserRole.CANDIDATE)
    created = await _patch(client, FULL_PROFILE)

    unchanged = await _patch(client, {})

    assert unchanged == created


async def test_profile_belongs_to_session_user(client: AsyncClient) -> None:
    """Личность берётся из сессии: чужой профиль не читается и не меняется."""
    await _login(client, 750010, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)

    await _login(client, 750011, UserRole.CANDIDATE)
    assert (await client.get("/api/candidate/profile")).status_code == 404

    own = await _patch(client, {"desired_role": "Официант", "user_id": 750010})

    assert own["user_id"] == 750011
    assert (await CandidateProfile.get(user_id=750010)).desired_role == "Бариста"


async def test_profile_change_keeps_screening_answers(client: AsyncClient) -> None:
    """Изменение профиля не переписывает исторические ответы отбора."""
    candidate = await _login(client, 750012, UserRole.CANDIDATE)
    await _patch(client, FULL_PROFILE)
    employer = await _employer()
    vacancy = await Vacancy.create(
        employer=employer, title="Бариста", status=VacancyStatus.PUBLISHED
    )
    question = await ScreeningQuestion.create(
        vacancy=vacancy,
        question="Готовы выйти в октябре?",
        type=ScreeningQuestionType.BOOLEAN,
        required=True,
        sort_order=1,
    )
    application = await Application.create(
        vacancy=vacancy, candidate=candidate, status=ApplicationStatus.SCREENING
    )
    answer = await ScreeningAnswer.create(
        application=application, question=question, value={"answer": True}
    )

    answered_at = answer.updated_at

    await _patch(client, {"available_from": "2027-01-01", "city": "Казань"})

    await answer.refresh_from_db()
    assert answer.value == {"answer": True}
    assert answer.updated_at == answered_at
    assert await ScreeningAnswer.filter(application=application).count() == 1


async def test_filled_profile_opens_feed(client: AsyncClient) -> None:
    """Этап 2 открывает вход в этап 3.

    Без профиля лента пуста, с профилем — показывает подходящую вакансию.
    """
    await _login(client, 750013, UserRole.CANDIDATE)
    employer = await _employer()
    vacancy = await Vacancy.create(
        employer=employer,
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )
    await VacancyCriterion.create(
        vacancy=vacancy,
        type=CriterionType.LOCATION,
        required=True,
        value={"city": "Москва"},
    )

    empty = await client.get("/api/vacancies/feed")
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    await _patch(client, FULL_PROFILE)

    feed = await client.get("/api/vacancies/feed")
    assert feed.status_code == 200
    assert "Бариста в центре" in [item["title"] for item in feed.json()["items"]]
