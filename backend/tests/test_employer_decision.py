"""Карточка кандидата и решение работодателя.

`GET /api/employer/vacancies/{id}/candidates`, `POST /api/applications/{id}/decision`.
Разделы 20, 26, 34, 35, 56 тех-доки.
"""

import asyncio
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications import employer_service
from app.applications.models import Application, EmployerDecision
from app.candidates.models import CandidateProfile
from app.core.database import utcnow
from app.core.enums import (
    ApplicationStatus,
    CriterionType,
    DecisionAction,
    ScreeningQuestionType,
    UserRole,
    VacancyStatus,
)
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(780000)
_candidate_ids = count(781000)

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
    await Vacancy.filter(employer_id__gte=780000, employer_id__lt=781000).delete()


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _employer(client: AsyncClient) -> User:
    """Работодатель, залогиненный в текущем клиенте."""
    return await _login(client, next(_employer_ids), UserRole.EMPLOYER)


async def _other_user(role: UserRole) -> User:
    """Пользователь без сессии в клиенте — для проверки чужих объектов."""
    user_id = next(_employer_ids) if role is UserRole.EMPLOYER else next(
        _candidate_ids
    )
    return await User.create(user_id=user_id, first_name="Другой", role=role)


async def _vacancy(
    employer: User,
    *,
    criteria: list[tuple[CriterionType, dict, bool]] | None = None,
    questions: list[tuple[str, ScreeningQuestionType]] | None = None,
) -> Vacancy:
    vacancy = await Vacancy.create(
        employer=employer,
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )
    for criterion_type, value, required in criteria or []:
        await VacancyCriterion.create(
            vacancy=vacancy, type=criterion_type, required=required, value=value
        )
    for order, (text, question_type) in enumerate(questions or [], start=1):
        await ScreeningQuestion.create(
            vacancy=vacancy,
            question=text,
            type=question_type,
            required=True,
            sort_order=order,
            validation_rules=None,
        )
    return vacancy


async def _candidate(*, profile: dict[str, Any] | None = None) -> User:
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    await CandidateProfile.create(
        user_id=candidate.user_id, **(FITTING_PROFILE if profile is None else profile)
    )
    return candidate


async def _application(
    vacancy: Vacancy,
    candidate: User,
    *,
    status: ApplicationStatus = ApplicationStatus.PASSED,
) -> Application:
    """Отклик создаётся напрямую: `POST /vacancies/:id/apply` — этап 3."""
    return await Application.create(
        vacancy=vacancy, candidate=candidate, status=status
    )


async def _screened_application(
    client: AsyncClient,
    vacancy: Vacancy,
    *,
    answers: list[Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[Application, User]:
    """Отклик, прошедший настоящий путь: отклик → первичный отбор.

    Нужен там, где проверяется содержимое карточки: снимок обязательных
    фильтров делает именно отбор, а не создание отклика.
    """
    candidate = await _candidate(profile=profile)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    created = await client.post(f"/api/vacancies/{vacancy.id}/apply")
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    questions = await ScreeningQuestion.filter(vacancy_id=vacancy.id).order_by(
        "sort_order"
    )
    passed = await client.post(
        f"/api/applications/{application_id}/screening",
        json={
            "answers": [
                {"question_id": question.id, "value": value}
                for question, value in zip(questions, answers or [], strict=True)
            ]
        },
    )
    assert passed.status_code == 200, passed.text
    return await Application.get(id=application_id), candidate


async def _relogin_employer(client: AsyncClient, employer: User) -> None:
    """Возвращает в клиент сессию работодателя после действий кандидата."""
    await _login(client, employer.user_id, UserRole.EMPLOYER)


async def _candidates(client: AsyncClient, vacancy: Vacancy, **params):
    return await client.get(
        f"/api/employer/vacancies/{vacancy.id}/candidates", params=params
    )


async def _decide(client: AsyncClient, application: Application, **payload):
    return await client.post(
        f"/api/applications/{application.id}/decision", json=payload
    )


# --- Доступ к списку кандидатов --------------------------------------------


async def test_candidates_require_session(client: AsyncClient) -> None:
    employer = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(employer)

    assert (await _candidates(client, vacancy)).status_code == 401


async def test_candidates_require_employer_role(client: AsyncClient) -> None:
    owner = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(owner)
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _candidates(client, vacancy)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_foreign_vacancy_candidates_are_not_visible(
    client: AsyncClient,
) -> None:
    """Чужая вакансия — 404: существование чужих вакансий не раскрывается."""
    owner = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(owner)
    await _application(vacancy, await _candidate())
    await _employer(client)

    response = await _candidates(client, vacancy)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_unknown_vacancy_returns_404(client: AsyncClient) -> None:
    await _employer(client)

    assert (
        await client.get("/api/employer/vacancies/999999/candidates")
    ).status_code == 404


# --- Состав списка ----------------------------------------------------------


async def test_only_candidates_past_screening_are_listed(
    client: AsyncClient,
) -> None:
    """Не прошедших обязательную фильтрацию работодатель не разбирает."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    shown = await _application(vacancy, await _candidate())
    for hidden_status in (
        ApplicationStatus.CREATED,
        ApplicationStatus.SCREENING,
        ApplicationStatus.HARD_FILTER_FAILED,
    ):
        await _application(vacancy, await _candidate(), status=hidden_status)

    body = (await _candidates(client, vacancy)).json()

    assert body["total"] == 1
    assert [item["application_id"] for item in body["items"]] == [shown.id]


async def test_candidates_of_other_vacancy_are_not_mixed_in(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    other_vacancy = await _vacancy(employer)
    mine = await _application(vacancy, await _candidate())
    await _application(other_vacancy, await _candidate())

    body = (await _candidates(client, vacancy)).json()

    assert [item["application_id"] for item in body["items"]] == [mine.id]


async def test_card_contains_profile_answers_and_hard_filters(
    client: AsyncClient,
) -> None:
    """Раздел 34: состав стандартизированной карточки."""
    employer = await _employer(client)
    vacancy = await _vacancy(
        employer,
        criteria=[
            (CriterionType.SCHEDULE, {"schedule": "full_time"}, True),
            (CriterionType.EXPERIENCE, {"min_months": 120}, False),
            (CriterionType.CERTIFICATE, {"name": "медкнижка"}, True),
        ],
        questions=[("Есть ли медкнижка?", ScreeningQuestionType.BOOLEAN)],
    )
    application, _ = await _screened_application(client, vacancy, answers=[True])
    question = await ScreeningQuestion.get(vacancy_id=vacancy.id)
    await _relogin_employer(client, employer)

    card = (await _candidates(client, vacancy)).json()["items"][0]

    assert card["application_id"] == application.id
    assert card["status"] == ApplicationStatus.PASSED.value
    assert card["desired_role"] == "Бариста"
    assert card["city"] == "Москва"
    assert card["salary"] == "70000.00"
    assert card["schedule"] == "full_time"
    assert card["experience_months"] == 24
    assert card["available_from"] == "2026-10-01"
    assert card["screening_answers"] == [
        {
            "question_id": question.id,
            "question": "Есть ли медкнижка?",
            "type": "boolean",
            "value": True,
        }
    ]
    assert card["hard_filters"] == [
        {"type": "schedule", "required": True, "passed": True},
        {"type": "experience", "required": False, "passed": False},
        # Сертификат по профилю не проверяется — подтверждается на отборе
        {"type": "certificate", "required": True, "passed": None},
    ]


async def test_card_does_not_expose_identity(client: AsyncClient) -> None:
    """Раздел 34 перечисляет только рабочие факторы: имени и фото в карточке нет."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    candidate = await _candidate()
    await User.filter(user_id=candidate.user_id).update(
        first_name="Иван", last_name="Петров", avatar_path="/app/storage/a.png"
    )
    await _application(vacancy, candidate)

    body = (await _candidates(client, vacancy)).json()

    assert "Иван" not in str(body)
    assert "Петров" not in str(body)
    assert "avatar" not in str(body)


async def test_card_without_profile_does_not_break_list(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Без профиля", role=UserRole.CANDIDATE
    )
    await _application(vacancy, candidate)

    card = (await _candidates(client, vacancy)).json()["items"][0]

    assert card["desired_role"] is None
    assert card["salary"] is None
    assert card["screening_answers"] == []


async def test_candidates_pagination(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    for _ in range(3):
        await _application(vacancy, await _candidate())

    first = (await _candidates(client, vacancy, limit=2, offset=0)).json()
    second = (await _candidates(client, vacancy, limit=2, offset=2)).json()

    assert first["total"] == 3 and second["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    first_ids = {item["application_id"] for item in first["items"]}
    assert first_ids.isdisjoint(
        {item["application_id"] for item in second["items"]}
    )


async def test_invalid_pagination_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    assert (await _candidates(client, vacancy, limit=0)).status_code == 422
    assert (await _candidates(client, vacancy, offset=-1)).status_code == 422


# --- Решение работодателя ---------------------------------------------------


async def test_invite_moves_application_and_writes_decision(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(client, application, action="invited")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.INVITED.value
    assert body["action"] == DecisionAction.INVITED.value
    assert body["reject_reason"] is None

    await application.refresh_from_db()
    assert application.status == ApplicationStatus.INVITED

    decision = await EmployerDecision.get(application_id=application.id)
    assert decision.action == DecisionAction.INVITED
    assert decision.reject_reason is None


async def test_reject_with_reason_is_saved(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(
        client, application, action="rejected", reject_reason="experience"
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.REJECTED.value

    decision = await EmployerDecision.get(application_id=application.id)
    assert decision.action == DecisionAction.REJECTED
    assert decision.reject_reason.value == "experience"


async def test_reject_without_reason_is_allowed(client: AsyncClient) -> None:
    """Причина отказа — P1, в P0 колонка остаётся nullable."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(client, application, action="rejected")

    assert response.status_code == 200, response.text
    decision = await EmployerDecision.get(application_id=application.id)
    assert decision.reject_reason is None


async def test_reserve_is_rejected_until_p1(client: AsyncClient) -> None:
    """Раздел 20: в P0 backend принимает только `rejected` и `invited`."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(client, application, action="reserved")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "decision_action_not_supported"
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.PASSED


async def test_unknown_action_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(client, application, action="maybe")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_reject_reason_without_rejection_is_refused(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(
        client, application, action="invited", reject_reason="salary"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reject_reason_not_applicable"


async def test_unknown_reject_reason_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(
        client, application, action="rejected", reject_reason="не понравился"
    )

    assert response.status_code == 422


# --- Переходы статусов ------------------------------------------------------


async def test_decision_before_screening_is_refused(client: AsyncClient) -> None:
    """Из `screening` решение принимать нельзя: отбор ещё не пройден."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.SCREENING
    )

    response = await _decide(client, application, action="invited")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
    assert response.json()["error"]["details"] == {
        "status": ApplicationStatus.SCREENING.value,
        "target": ApplicationStatus.INVITED.value,
    }


async def test_decision_on_failed_screening_is_refused(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.HARD_FILTER_FAILED
    )

    assert (await _decide(client, application, action="invited")).status_code == 409


async def test_decision_cannot_be_taken_twice(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())
    assert (await _decide(client, application, action="invited")).status_code == 200

    repeated = await _decide(client, application, action="rejected")

    assert repeated.status_code == 409
    assert await EmployerDecision.filter(application_id=application.id).count() == 1


async def test_concurrent_decisions_produce_one(client: AsyncClient) -> None:
    """Два одновременных нажатия не должны дать два решения."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    responses = await asyncio.gather(
        *[_decide(client, application, action="invited") for _ in range(4)]
    )

    assert sorted(response.status_code for response in responses) == [
        200,
        409,
        409,
        409,
    ]
    assert await EmployerDecision.filter(application_id=application.id).count() == 1
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.INVITED


# --- Права на решение -------------------------------------------------------


async def test_decision_requires_session(client: AsyncClient) -> None:
    employer = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    assert (await _decide(client, application, action="invited")).status_code == 401


async def test_candidate_cannot_decide(client: AsyncClient) -> None:
    owner = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(owner)
    candidate = await _candidate()
    application = await _application(vacancy, candidate)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _decide(client, application, action="invited")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_foreign_application_cannot_be_decided(client: AsyncClient) -> None:
    owner = await _other_user(UserRole.EMPLOYER)
    vacancy = await _vacancy(owner)
    application = await _application(vacancy, await _candidate())
    await _employer(client)

    response = await _decide(client, application, action="invited")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "application_not_found"
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.PASSED


async def test_unknown_application_returns_404(client: AsyncClient) -> None:
    await _employer(client)

    response = await client.post(
        "/api/applications/999999/decision", json={"action": "invited"}
    )

    assert response.status_code == 404


# --- Аналитика --------------------------------------------------------------


async def test_decision_writes_analytics_event(client: AsyncClient) -> None:
    """Раздел 60: `candidate_invited` / `candidate_rejected`."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    invited = await _application(vacancy, await _candidate())
    rejected = await _application(vacancy, await _candidate())

    await _decide(client, invited, action="invited")
    await _decide(client, rejected, action="rejected", reject_reason="salary")

    events = await AnalyticsEvent.filter(user_id=employer.user_id).order_by("id")
    assert [event.event_name for event in events] == [
        "candidate_invited",
        "candidate_rejected",
    ]
    assert events[-1].payload["reject_reason"] == "salary"


# --- Список после решения ---------------------------------------------------


async def test_decided_candidate_stays_in_list_with_new_status(
    client: AsyncClient,
) -> None:
    """Фронт обновляет список после решения и должен видеть новый статус."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())
    await _decide(client, application, action="rejected")

    body = (await _candidates(client, vacancy)).json()

    assert body["total"] == 1
    assert body["items"][0]["status"] == ApplicationStatus.REJECTED.value


async def test_stale_status_is_caught_under_lock(
    client: AsyncClient, monkeypatch
) -> None:
    """Проверка перехода до транзакции могла прочитать устаревший статус.

    Воспроизводим именно это: запрос считает отклик в `passed`, а в базе он
    уже `invited`. Отклонить его обязан повторный контроль под блокировкой —
    параллельный прогон такую последовательность не гарантирует.
    """
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.INVITED
    )

    stale = Application(
        id=application.id,
        vacancy_id=vacancy.id,
        candidate_id=application.candidate_id,
        status=ApplicationStatus.PASSED,
    )

    async def _stale_application(*_args, **_kwargs) -> Application:
        return stale

    monkeypatch.setattr(
        employer_service, "_own_application", _stale_application
    )

    response = await _decide(client, application, action="rejected")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
    assert await EmployerDecision.filter(application_id=application.id).count() == 0


async def test_pages_do_not_overlap_for_equal_applied_at(
    client: AsyncClient,
) -> None:
    """Одинаковое время отклика не должно ломать постраничную выдачу."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    for _ in range(4):
        await _application(vacancy, await _candidate())
    moment = utcnow()
    await Application.filter(vacancy_id=vacancy.id).update(created_at=moment)

    seen: list[int] = []
    for offset in (0, 2):
        page = (await _candidates(client, vacancy, limit=2, offset=offset)).json()
        seen.extend(item["application_id"] for item in page["items"])

    assert len(seen) == 4
    assert len(set(seen)) == 4


async def test_card_keeps_screening_result_after_profile_change(
    client: AsyncClient,
) -> None:
    """Кандидат прошёл отбор — работодатель видит его прошедшим.

    Изменение профиля после отбора не переписывает результат обязательных
    фильтров: иначе карточка противоречила бы статусу отклика.
    """
    employer = await _employer(client)
    vacancy = await _vacancy(
        employer,
        criteria=[(CriterionType.SCHEDULE, {"schedule": "full_time"}, True)],
        questions=[("Есть ли медкнижка?", ScreeningQuestionType.BOOLEAN)],
    )
    application, _ = await _screened_application(client, vacancy, answers=[True])
    assert application.status == ApplicationStatus.PASSED

    # Кандидат меняет график на тот, который вакансии не подходит
    changed = await client.patch(
        "/api/candidate/profile", json={"schedule": "night"}
    )
    assert changed.status_code == 200, changed.text
    await _relogin_employer(client, employer)

    card = (await _candidates(client, vacancy)).json()["items"][0]

    assert card["status"] == ApplicationStatus.PASSED.value
    assert card["hard_filters"] == [
        {"type": "schedule", "required": True, "passed": True}
    ]
    # Данные профиля при этом живые: работодатель связывается с человеком,
    # а не со слепком на момент отбора
    assert card["schedule"] == "night"


async def test_decision_still_possible_after_profile_change(
    client: AsyncClient,
) -> None:
    """Прошедшего отбор кандидата можно пригласить, что бы он ни менял потом."""
    employer = await _employer(client)
    vacancy = await _vacancy(
        employer,
        criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)],
        questions=[("Есть ли медкнижка?", ScreeningQuestionType.BOOLEAN)],
    )
    application, _ = await _screened_application(client, vacancy, answers=[True])
    await client.patch("/api/candidate/profile", json={"city": "Казань"})
    await _relogin_employer(client, employer)

    response = await _decide(client, application, action="invited")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.INVITED.value
