"""GET/PATCH /api/candidate/profile. Разделы 14, 27 тех-доки.

Guard'ы и весь путь создания/редактирования профиля собраны в сквозные
сценарии. Гонки при первом сохранении оставлены отдельными тестами — там
важна изолированная диагностика конкретной гонки, а не компактность.
"""

import asyncio
from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient

from app.applications.models import Application, ScreeningAnswer
from app.candidates import service
from app.candidates.models import CandidateProfile
from app.candidates.schemas import CandidateProfileUpdateRequest
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


# --- Доступ --------------------------------------------------------------------


async def test_profile_access_guards(client: AsyncClient) -> None:
    # 1. Без сессии профиль недоступен вовсе
    assert (await client.get("/api/candidate/profile")).status_code == 401
    assert (
        await client.patch("/api/candidate/profile", json={"city": "Москва"})
    ).status_code == 401

    # 2. Без выбранной роли и с чужой ролью — тоже нет
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

    # 3. У кандидата без профиля GET возвращает 404
    await _login(client, 750002, UserRole.CANDIDATE)
    response = await client.get("/api/candidate/profile")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "candidate_profile_not_found"


# --- Создание и редактирование --------------------------------------------------


async def test_profile_create_and_update_flow(client: AsyncClient) -> None:
    # 1. Без desired_role профиль создать нельзя
    await _login(client, 750004, UserRole.CANDIDATE)
    missing_role = await client.patch(
        "/api/candidate/profile", json={"city": "Москва"}
    )
    assert missing_role.status_code == 422
    assert missing_role.json()["error"]["code"] == "desired_role_required"
    assert await CandidateProfile.get_or_none(user_id=750004) is None

    # 2. PATCH создаёт профиль с переданными полями
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

    # 3. Частичное обновление меняет только переданные поля
    updated = await _patch(client, {"salary": "85000"})
    assert updated["salary"] == "85000.00"
    assert updated["desired_role"] == "Бариста"
    assert updated["city"] == "Москва"
    assert updated["experience_months"] == 24
    assert updated["updated_at"] >= updated["created_at"]

    # 4. Явный null очищает необязательное поле
    await _patch(client, FULL_PROFILE)
    cleared = await _patch(client, {"city": None, "available_from": None})
    assert cleared["city"] is None
    assert cleared["available_from"] is None
    assert cleared["schedule"] == "full_time"

    # 5. Пустая строка — тоже очистка, но не для обязательной желаемой должности
    await _patch(client, FULL_PROFILE)
    blank_city = await _patch(client, {"city": "   "})
    assert blank_city["city"] is None
    blank_role = await client.patch(
        "/api/candidate/profile", json={"desired_role": " "}
    )
    assert blank_role.status_code == 422
    assert (await CandidateProfile.get(user_id=750003)).desired_role == "Бариста"

    # 6. Некорректные значения отклоняются, ничего не сохраняется
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
    stored_after_invalid = await CandidateProfile.get(user_id=750003)
    assert stored_after_invalid.salary == Decimal("70000.00")
    assert stored_after_invalid.experience_months == 24

    # 7. Пустой PATCH ничего не меняет
    baseline = await _patch(client, FULL_PROFILE)
    unchanged = await _patch(client, {})
    assert unchanged == baseline

    # 8. Личность берётся из сессии: чужой профиль не читается и не меняется
    await _login(client, 750011, UserRole.CANDIDATE)
    assert (await client.get("/api/candidate/profile")).status_code == 404
    own = await _patch(client, {"desired_role": "Официант", "user_id": 750003})
    assert own["user_id"] == 750011
    assert (await CandidateProfile.get(user_id=750003)).desired_role == "Бариста"


# --- Взаимодействие с отбором и лентой ------------------------------------------


async def test_profile_downstream_interactions(client: AsyncClient) -> None:
    # 1. Изменение профиля не переписывает исторические ответы отбора
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

    # 2. Этап 2 открывает вход в этап 3: без профиля лента пуста, с профилем
    # показывает подходящую вакансию
    await _login(client, 750013, UserRole.CANDIDATE)
    feed_vacancy = await Vacancy.create(
        employer=employer,
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )
    await VacancyCriterion.create(
        vacancy=feed_vacancy,
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


# --- Гонки при первом сохранении (диагностика важнее компактности) ------------


async def test_concurrent_creation_makes_one_profile(client: AsyncClient) -> None:
    """Параллельные первые сохранения не должны падать и плодить профили.

    Такая же гонка однажды была в первой авторизации (`_upsert_user`).
    """
    await _login(client, 750014, UserRole.CANDIDATE)

    responses = await asyncio.gather(
        *[
            client.patch("/api/candidate/profile", json=FULL_PROFILE)
            for _ in range(5)
        ]
    )

    assert [response.status_code for response in responses] == [200] * 5
    assert await CandidateProfile.filter(user_id=750014).count() == 1


async def test_profile_created_between_read_and_insert_is_reused(
    client: AsyncClient,
) -> None:
    """Состояние проигравшего гонку: профиль появился после чтения, до вставки.

    Воспроизвести это через HTTP нельзя — вызываем ту же ветку сервиса
    напрямую, чтобы вставка гарантированно наткнулась на существующую запись.
    """
    user = await _login(client, 750015, UserRole.CANDIDATE)
    await CandidateProfile.create(
        user_id=user.user_id, desired_role="Бариста", city="Москва"
    )

    payload = CandidateProfileUpdateRequest(desired_role="Официант")
    profile = await service._create_profile(
        user, payload.model_dump(exclude_unset=True)
    )

    assert profile.desired_role == "Официант"
    assert profile.city == "Москва"
    assert await CandidateProfile.filter(user_id=user.user_id).count() == 1
