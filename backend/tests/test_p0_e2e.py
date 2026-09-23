"""Сквозной маршрут P0: от авторизации до назначенного собеседования.

Раздел 80 (E2E) и раздел 82 (демо-сценарий) тех-доки. Здесь backend-часть
общего E2E: два пользователя с разными сессиями проходят весь обязательный
путь только через HTTP API, без обращения к моделям напрямую там, где это
делает продукт.

Конечный результат — `Interview scheduled` (раздел 1).
"""

from datetime import date, timedelta
from itertools import count
from typing import Any, AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import utcnow
from app.core.enums import ApplicationStatus, NotificationType, UserRole
from app.interviews.models import Interview, InterviewSlot
from app.main import app
from app.notifications.models import NotificationLog
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload
from tests.fakes import RecordingTransport

EMPLOYER_ID = 820000
CANDIDATE_ID = 821000
_run = count(1)


@pytest_asyncio.fixture
async def employer_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def candidate_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies() -> AsyncIterator[None]:
    """Собеседования удаляются первыми: `interviews.slot_id` защищён `RESTRICT`."""
    yield
    vacancy_ids = await Vacancy.filter(
        employer_id__gte=820000, employer_id__lt=821000
    ).values_list("id", flat=True)
    if not vacancy_ids:
        return
    slot_ids = await InterviewSlot.filter(vacancy_id__in=vacancy_ids).values_list(
        "id", flat=True
    )
    if slot_ids:
        await Interview.filter(slot_id__in=slot_ids).delete()
    await Vacancy.filter(id__in=vacancy_ids).delete()


async def _auth(client: AsyncClient, user_id: int) -> dict[str, Any]:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _choose_role(client: AsyncClient, role: UserRole) -> dict[str, Any]:
    response = await client.patch("/api/users/me/role", json={"role": role.value})
    assert response.status_code == 200, response.text
    return response.json()


async def _current_step(client: AsyncClient, user_id: int) -> str:
    """Шаг сценария при повторном открытии Mini App (раздел 7)."""
    return (await _auth(client, user_id))["current_step"]


async def test_full_p0_route(
    employer_client: AsyncClient,
    candidate_client: AsyncClient,
    notifications: RecordingTransport,
) -> None:
    run = next(_run)
    employer_id = EMPLOYER_ID + run
    candidate_id = CANDIDATE_ID + run

    # 1. Работодатель: авторизация и выбор роли
    first_auth = await _auth(employer_client, employer_id)
    assert first_auth["user"]["role"] is None
    assert first_auth["current_step"] == "role_selection"
    await _choose_role(employer_client, UserRole.EMPLOYER)
    assert await _current_step(employer_client, employer_id) == "vacancy_create"

    # 2. Создание вакансии с обязательными условиями и вопросами отбора
    created = await employer_client.post(
        "/api/vacancies",
        json={
            "title": "Бариста в центре",
            "location": "Москва",
            "salary_min": "60000",
            "salary_max": "90000",
            "schedule": "full_time",
            "criteria": [
                {"type": "location", "required": True, "value": {"city": "Москва"}},
                {"type": "experience", "required": True, "value": {"min_months": 12}},
            ],
            "questions": [
                {
                    "question": "Есть ли действующая медкнижка?",
                    "type": "boolean",
                    "required": True,
                    "validation_rules": {"must_equal": True},
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    vacancy = created.json()
    assert vacancy["status"] == "draft"

    # 3. Публикация
    published = await employer_client.patch(
        f"/api/vacancies/{vacancy['id']}", json={"status": "published"}
    )
    assert published.status_code == 200, published.text
    assert published.json()["public_url"]
    assert await _current_step(employer_client, employer_id) == "employer_home"

    # 4. Кандидат: авторизация, роль, профиль
    assert (await _auth(candidate_client, candidate_id))["current_step"] == (
        "role_selection"
    )
    await _choose_role(candidate_client, UserRole.CANDIDATE)
    assert await _current_step(candidate_client, candidate_id) == "candidate_profile"

    profile = await candidate_client.patch(
        "/api/candidate/profile",
        json={
            "desired_role": "Бариста",
            "city": "Москва",
            "salary": "70000",
            "schedule": "full_time",
            "experience_months": 24,
            "available_from": date.today().isoformat(),
        },
    )
    assert profile.status_code == 200, profile.text
    assert await _current_step(candidate_client, candidate_id) == "feed"

    # 5. Лента и отклик
    feed = await candidate_client.get("/api/vacancies/feed")
    assert feed.status_code == 200, feed.text
    assert vacancy["id"] in [item["id"] for item in feed.json()["items"]]

    applied = await candidate_client.post(f"/api/vacancies/{vacancy['id']}/apply")
    assert applied.status_code == 201, applied.text
    application_id = applied.json()["id"]
    assert applied.json()["status"] == ApplicationStatus.SCREENING.value

    # 6. Первичный отбор и обязательные фильтры
    screening = await candidate_client.get(
        f"/api/applications/{application_id}/screening"
    )
    assert screening.status_code == 200, screening.text
    question = screening.json()["questions"][0]
    # Отсекающее условие вакансии кандидату не показывается
    assert "must_equal" not in question["rules"]

    passed = await candidate_client.post(
        f"/api/applications/{application_id}/screening",
        json={"answers": [{"question_id": question["id"], "value": True}]},
    )
    assert passed.status_code == 200, passed.text
    assert passed.json()["status"] == ApplicationStatus.PASSED.value
    assert await _current_step(candidate_client, candidate_id) == "application_status"

    # 7. Карточка кандидата у работодателя
    candidates = await employer_client.get(
        f"/api/employer/vacancies/{vacancy['id']}/candidates"
    )
    assert candidates.status_code == 200, candidates.text
    card = candidates.json()["items"][0]
    assert card["application_id"] == application_id
    assert card["hard_filters"] == [
        {"type": "location", "required": True, "passed": True},
        {"type": "experience", "required": True, "passed": True},
    ]

    # 8. Приглашение: решение, match и взаимный интерес одной операцией
    decision = await employer_client.post(
        f"/api/applications/{application_id}/decision", json={"action": "invited"}
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == ApplicationStatus.MUTUAL_INTEREST.value
    match_id = decision.json()["match_id"]
    assert match_id is not None

    # 9. Работодатель предлагает время
    starts_at = utcnow() + timedelta(days=1)
    slot = await employer_client.post(
        f"/api/vacancies/{vacancy['id']}/slots",
        json={
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        },
    )
    assert slot.status_code == 201, slot.text
    slot_id = slot.json()["id"]

    # 10. Кандидат видит время и бронирует
    slots = await candidate_client.get(f"/api/vacancies/{vacancy['id']}/slots")
    assert slots.status_code == 200, slots.text
    assert [item["id"] for item in slots.json()["items"]] == [slot_id]
    assert slots.json()["match_id"] == match_id

    booked = await candidate_client.post(
        f"/api/matches/{match_id}/book", json={"slot_id": slot_id}
    )
    assert booked.status_code == 201, booked.text
    interview = booked.json()
    assert interview["status"] == "scheduled"
    assert interview["application_status"] == (
        ApplicationStatus.INTERVIEW_SCHEDULED.value
    )

    # 11. Занятый слот больше не предлагается, а собеседование видно обеим сторонам
    candidate_view = (
        await candidate_client.get(f"/api/vacancies/{vacancy['id']}/slots")
    ).json()
    assert candidate_view["items"] == []
    assert candidate_view["interviews"][0]["slot"]["id"] == slot_id

    employer_view = (
        await employer_client.get(f"/api/vacancies/{vacancy['id']}/slots")
    ).json()
    assert employer_view["interviews"][0]["application_id"] == application_id

    # 12. Уведомления P0 (раздел 46) отправлены обеим сторонам
    sent_types = set(
        await NotificationLog.filter(
            user_id__in=[employer_id, candidate_id]
        ).values_list("event_type", flat=True)
    )
    assert sent_types == {
        NotificationType.APPLICATION_CREATED,
        NotificationType.CANDIDATE_INVITED,
        NotificationType.MUTUAL_INTEREST,
        NotificationType.INTERVIEW_SLOT_AVAILABLE,
        NotificationType.INTERVIEW_BOOKED,
    }
    assert notifications.texts_for(candidate_id)
    assert notifications.texts_for(employer_id)

    # 13. Повторное открытие Mini App возвращает обоих на актуальный шаг
    assert await _current_step(candidate_client, candidate_id) == "application_status"
    assert await _current_step(employer_client, employer_id) == "employer_home"

    # 14. Роли и личности не перепутаны: чужой отклик работодателю не принадлежит
    foreign = await candidate_client.post(
        f"/api/applications/{application_id}/decision", json={"action": "rejected"}
    )
    assert foreign.status_code == 403
    assert (await User.get(user_id=candidate_id)).role is UserRole.CANDIDATE
