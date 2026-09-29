"""Статус отклика кандидата после перезагрузки экрана.

`GET /api/applications/{id}` — эндпоинта в тех-доке (раздел 27) и в текущем
`app/applications/router.py` нет вовсе, хотя фронтенд уже определяет под него
контракт `CandidateApplication` (`frontend/src/api/hiring.ts`) и рисует экран
C06 «Не подошло» (`ApplicationStatusPage.tsx`) по этим данным.

Баг с демо: после перезагрузки экран C06 не показывает причину отказа —
`failed_criteria` первичного отбора возвращается только один раз, синхронно,
в ответе `POST /applications/{id}/screening` (`ScreeningResultResponse`).
Сам отклик при этом хранит снимок (`Application.hard_filter_result`), но
прочитать его обратно нечем: перезагрузка страницы отправляет кандидата в
никуда.

Тесты фиксируют контракт `GET /applications/{id}` (кандидат, только свой
отклик) по форме `CandidateApplication` из hiring.ts: `status`,
`failed_criteria`, `vacancy`, `match_id`, `interview_id`. До реализации
эндпоинта они падают на 404 — это ожидаемо и есть сама демонстрация бага.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.applications.models import Application, Match
from app.candidates.models import CandidateProfile
from app.core.enums import (
    ApplicationStatus,
    CriterionType,
    InterviewSlotStatus,
    InterviewStatus,
    UserRole,
    VacancyStatus,
)
from app.interviews.models import Interview, InterviewSlot
from app.main import app
from app.users.models import User
from app.vacancies.models import Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(860000)
_candidate_ids = count(861000)

MOSCOW_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": date(2026, 10, 1),
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    yield
    # `Interview.slot` — RESTRICT: вакансия с интервью не удалится, пока
    # интервью само не убрано (в отличие от Application/Match, которые
    # каскадно чистятся вместе с вакансией).
    slot_ids = await InterviewSlot.filter(
        vacancy__employer_id__gte=860000, vacancy__employer_id__lt=861000
    ).values_list("id", flat=True)
    if slot_ids:
        await Interview.filter(slot_id__in=slot_ids).delete()
    await Vacancy.filter(employer_id__gte=860000, employer_id__lt=861000).delete()


def _fresh_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _employer(client: AsyncClient) -> User:
    return await _login(client, next(_employer_ids), UserRole.EMPLOYER)


async def _candidate(
    client: AsyncClient, *, profile: dict[str, Any] | None = None
) -> User:
    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await CandidateProfile.create(
        user_id=candidate.user_id, **(MOSCOW_PROFILE if profile is None else profile)
    )
    return candidate


async def _vacancy_requiring_moscow(employer: User) -> Vacancy:
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
    return vacancy


async def _apply_and_screen(client: AsyncClient, vacancy: Vacancy) -> int:
    created = await client.post(f"/api/vacancies/{vacancy.id}/apply")
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    screened = await client.post(
        f"/api/applications/{application_id}/screening", json={"answers": []}
    )
    assert screened.status_code == 200, screened.text
    return application_id


async def _get_application(client: AsyncClient, application_id: int):
    return await client.get(f"/api/applications/{application_id}")


# --- Права доступа --------------------------------------------------------------


async def test_application_detail_guards() -> None:
    async with _fresh_client() as setup_client:
        employer = await _employer(setup_client)
        vacancy = await _vacancy_requiring_moscow(employer)

    async with _fresh_client() as owner_client:
        await _candidate(owner_client, profile=MOSCOW_PROFILE)
        application_id = await _apply_and_screen(owner_client, vacancy)

        # 1. Без сессии — 401
        async with _fresh_client() as guest:
            guest_response = await _get_application(guest, application_id)
        assert guest_response.status_code == 401

        # 2. Работодателю эндпоинт недоступен — это данные кандидата о своём отклике
        async with _fresh_client() as as_employer:
            await _login(as_employer, employer.user_id, UserRole.EMPLOYER)
            employer_response = await _get_application(as_employer, application_id)
        assert employer_response.status_code == 403
        assert employer_response.json()["error"]["code"] == "wrong_role"

        # 3. Чужой отклик — 404, а не 403: существование чужих откликов не раскрывается
        other_candidate = await User.create(
            user_id=next(_candidate_ids), first_name="Другой", role=UserRole.CANDIDATE
        )
        async with _fresh_client() as as_other:
            await _login(as_other, other_candidate.user_id, UserRole.CANDIDATE)
            foreign_response = await _get_application(as_other, application_id)
        assert foreign_response.status_code == 404
        assert foreign_response.json()["error"]["code"] == "application_not_found"

        # 4. Несуществующий отклик — тоже 404
        unknown_response = await _get_application(owner_client, 999999)
        assert unknown_response.status_code == 404
        assert unknown_response.json()["error"]["code"] == "application_not_found"


# --- Основной баг: причина отказа теряется после перезагрузки -------------------


async def test_application_detail_survives_reload_after_hard_filter_failure() -> None:
    """Кандидат из Казани не проходит обязательное условие «Москва».

    `POST /applications/{id}/screening` в моменте отдаёт `failed_criteria`
    (это уже работает — см. `test_screening.py`). Проверяем именно то, чего
    сейчас нет: тот же результат должен читаться повторно, как при
    перезагрузке экрана C06.
    """
    async with _fresh_client() as employer_client:
        employer = await _employer(employer_client)
        vacancy = await _vacancy_requiring_moscow(employer)

    async with _fresh_client() as candidate_client:
        await _candidate(
            candidate_client, profile=MOSCOW_PROFILE | {"city": "Казань"}
        )

        created = await candidate_client.post(f"/api/vacancies/{vacancy.id}/apply")
        assert created.status_code == 201, created.text
        application_id = created.json()["id"]

        screened = await candidate_client.post(
            f"/api/applications/{application_id}/screening", json={"answers": []}
        )
        assert screened.status_code == 200, screened.text
        assert screened.json()["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
        assert screened.json()["failed_criteria"] == [CriterionType.LOCATION.value]

        # "Перезагрузка": тот же результат должен быть виден без повторного
        # прохождения отбора — POST нельзя вызвать дважды (`screening_already_completed`).
        reloaded = await _get_application(candidate_client, application_id)

    assert reloaded.status_code == 200, reloaded.text
    body = reloaded.json()
    assert body["id"] == application_id
    assert body["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
    assert body["failed_criteria"] == [CriterionType.LOCATION.value]
    assert body["vacancy"]["id"] == vacancy.id
    assert body["vacancy"]["title"] == vacancy.title
    assert any(
        criterion["type"] == CriterionType.LOCATION.value
        for criterion in body["vacancy"]["criteria"]
    )
    assert body["match_id"] is None
    assert body["interview_id"] is None


# --- Остальные статусы: match_id и interview_id ---------------------------------


async def test_application_detail_reflects_match_and_interview() -> None:
    async with _fresh_client() as employer_client:
        employer = await _employer(employer_client)
        vacancy = await _vacancy_requiring_moscow(employer)

    async with _fresh_client() as candidate_client:
        candidate = await _candidate(candidate_client, profile=MOSCOW_PROFILE)
        application_id = await _apply_and_screen(candidate_client, vacancy)

        # 1. Прошёл отбор, решения ещё нет: пусто, но не ошибка
        pending = await _get_application(candidate_client, application_id)
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == ApplicationStatus.PASSED.value
        assert pending.json()["failed_criteria"] == []
        assert pending.json()["match_id"] is None
        assert pending.json()["interview_id"] is None

    # 2. Работодатель приглашает — появляется match_id
    async with _fresh_client() as employer_client:
        await _login(employer_client, employer.user_id, UserRole.EMPLOYER)
        decision = await employer_client.post(
            f"/api/applications/{application_id}/decision", json={"action": "invited"}
        )
        assert decision.status_code == 200, decision.text
        match_id = decision.json()["match_id"]
        assert match_id is not None

    async with _fresh_client() as candidate_client:
        await _login(candidate_client, candidate.user_id, UserRole.CANDIDATE)
        invited = await _get_application(candidate_client, application_id)
        assert invited.status_code == 200, invited.text
        assert invited.json()["status"] == ApplicationStatus.MUTUAL_INTEREST.value
        assert invited.json()["match_id"] == match_id
        assert invited.json()["interview_id"] is None

        # 3. Назначенное интервью — появляется interview_id
        slot = await InterviewSlot.create(
            employer_id=employer.user_id,
            vacancy_id=vacancy.id,
            starts_at=datetime(2026, 10, 5, 10, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 5, 10, 30, tzinfo=timezone.utc),
            status=InterviewSlotStatus.BOOKED,
        )
        match = await Match.get(id=match_id)
        interview = await Interview.create(
            match=match, slot=slot, status=InterviewStatus.SCHEDULED
        )
        await Application.filter(id=application_id).update(
            status=ApplicationStatus.INTERVIEW_SCHEDULED
        )

        scheduled = await _get_application(candidate_client, application_id)
        assert scheduled.status_code == 200, scheduled.text
        assert scheduled.json()["status"] == ApplicationStatus.INTERVIEW_SCHEDULED.value
        assert scheduled.json()["match_id"] == match_id
        assert scheduled.json()["interview_id"] == interview.id

        # 4. В списке «Мои отклики» — заведение, фото и время интервью
        listed = await candidate_client.get("/api/applications")
        assert listed.status_code == 200, listed.text
        [item] = listed.json()["items"]
        assert item["id"] == application_id
        assert item["company_name"] == vacancy.company_name
        assert item["image_url"] == vacancy.image_url
        assert item["interview_starts_at"] is not None
        assert datetime.fromisoformat(item["interview_starts_at"]) == slot.starts_at
