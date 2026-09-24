"""Карточка кандидата, решение работодателя и взаимный интерес.

`GET /api/employer/vacancies/{id}/candidates`, `POST /api/applications/{id}/decision`.
Разделы 20, 26, 34, 35, 36, 56 тех-доки.

Тесты сгруппированы по сквозным сценариям: guard'ы одного эндпоинта, весь
invite-flow, весь reject-flow — в одной функции с пронумерованными шагами.
Отдельными тестами остаются только конкурентность и специально
воспроизводимые гонки состояния — там диагностика важнее компактности.
"""

import asyncio
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications import employer_service
from app.applications.models import Application, EmployerDecision, Match
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
from app.main import app
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload
from tests.fakes import RecordingTransport

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


def _fresh_client() -> AsyncClient:
    """Отдельная сессия: гостю и кандидату нельзя делить cookie с работодателем."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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


# --- Доступ к списку кандидатов ----------------------------------------------


async def test_candidates_list_access_and_guards(client: AsyncClient) -> None:
    # 1. Без сессии список недоступен
    owner = await _other_user(UserRole.EMPLOYER)
    guest_vacancy = await _vacancy(owner)
    async with _fresh_client() as guest:
        assert (await _candidates(guest, guest_vacancy)).status_code == 401

    # 2. Кандидату список недоступен вовсе
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    wrong_role = await _candidates(client, guest_vacancy)
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    # 3. Чужая вакансия — 404: существование чужих вакансий не раскрывается
    await _application(guest_vacancy, await _candidate())
    employer = await _employer(client)
    foreign = await _candidates(client, guest_vacancy)
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "vacancy_not_found"

    # 4. Несуществующая вакансия — тоже 404
    assert (
        await client.get("/api/employer/vacancies/999999/candidates")
    ).status_code == 404

    # 5. Некорректная пагинация отклоняется
    own_vacancy = await _vacancy(employer)
    assert (await _candidates(client, own_vacancy, limit=0)).status_code == 422
    assert (await _candidates(client, own_vacancy, offset=-1)).status_code == 422


# --- Состав списка -------------------------------------------------------------


async def test_candidates_list_content(client: AsyncClient) -> None:
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
    other_vacancy = await _vacancy(employer)

    # 1. Не прошедшие обязательную фильтрацию в списке не появляются
    for hidden_status in (
        ApplicationStatus.CREATED,
        ApplicationStatus.SCREENING,
        ApplicationStatus.HARD_FILTER_FAILED,
    ):
        await _application(vacancy, await _candidate(), status=hidden_status)
    # Отклик по другой вакансии того же работодателя тоже не должен попасть
    await _application(other_vacancy, await _candidate())

    # 2. Карточка содержит ответы отбора и снимок обязательных фильтров
    application, _ = await _screened_application(client, vacancy, answers=[True])
    question = await ScreeningQuestion.get(vacancy_id=vacancy.id)
    await _relogin_employer(client, employer)

    body = (await _candidates(client, vacancy)).json()
    assert body["total"] == 1
    card = body["items"][0]
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

    # 3. Карточка не раскрывает личность: ни имени, ни фото
    assert "Иван" not in str(body)
    identified_candidate = await _candidate()
    await User.filter(user_id=identified_candidate.user_id).update(
        first_name="Иван", last_name="Петров", avatar_path="/app/storage/a.png"
    )
    await _application(vacancy, identified_candidate)
    identity_body = (await _candidates(client, vacancy)).json()
    assert "Иван" not in str(identity_body)
    assert "Петров" not in str(identity_body)
    assert "avatar" not in str(identity_body)

    # 4. Отсутствие профиля не ломает список — поля просто пустые
    profileless = await User.create(
        user_id=next(_candidate_ids), first_name="Без профиля", role=UserRole.CANDIDATE
    )
    profileless_application = await _application(vacancy, profileless)
    profileless_card = next(
        item
        for item in (await _candidates(client, vacancy)).json()["items"]
        if item["application_id"] == profileless_application.id
    )
    assert profileless_card["desired_role"] is None
    assert profileless_card["salary"] is None
    assert profileless_card["screening_answers"] == []

    # 5. Пагинация не пересекается и корректно считает total
    pagination_vacancy = await _vacancy(employer)
    for _ in range(3):
        await _application(pagination_vacancy, await _candidate())
    first_page = (await _candidates(client, pagination_vacancy, limit=2, offset=0)).json()
    second_page = (
        await _candidates(client, pagination_vacancy, limit=2, offset=2)
    ).json()
    assert first_page["total"] == 3 and second_page["total"] == 3
    assert len(first_page["items"]) == 2 and len(second_page["items"]) == 1
    assert {item["application_id"] for item in first_page["items"]}.isdisjoint(
        {item["application_id"] for item in second_page["items"]}
    )

    # 6. Изменение профиля после отбора не переписывает уже снятый результат
    await _login(client, application.candidate_id, UserRole.CANDIDATE)
    changed = await client.patch("/api/candidate/profile", json={"schedule": "night"})
    assert changed.status_code == 200, changed.text
    await _relogin_employer(client, employer)
    refreshed_card = next(
        item for item in (await _candidates(client, vacancy)).json()["items"]
        if item["application_id"] == application.id
    )
    assert refreshed_card["status"] == ApplicationStatus.PASSED.value
    # Обязательные фильтры не пересчитываются задним числом
    assert refreshed_card["hard_filters"][0] == {
        "type": "schedule", "required": True, "passed": True,
    }
    # Данные профиля при этом живые: работодатель связывается с человеком
    assert refreshed_card["schedule"] == "night"


# --- Ranking и объяснимость (P1, разделы 64, 65) --------------------------------


async def test_ranking_orders_by_desirable_criteria(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(
        employer,
        criteria=[
            (CriterionType.SCHEDULE, {"schedule": "full_time"}, True),
            (CriterionType.LOCATION, {"city": "Москва"}, False),
            (CriterionType.EXPERIENCE, {"min_months": 12}, False),
        ],
    )
    await VacancyCriterion.filter(
        vacancy_id=vacancy.id, type=CriterionType.EXPERIENCE
    ).update(weight=Decimal("2"))

    # Проходит оба желательных критерия — самый высокий score
    best = await _application(
        vacancy,
        await _candidate(
            profile=FITTING_PROFILE | {"experience_months": 24}
        ),
    )
    # Проходит только зарплату/локацию, опыта не хватает
    middle = await _application(
        vacancy,
        await _candidate(
            profile=FITTING_PROFILE | {"experience_months": 1}
        ),
    )
    # Не проходит ни один желательный критерий
    worst = await _application(
        vacancy,
        await _candidate(
            profile=FITTING_PROFILE | {"city": "Казань", "experience_months": 1}
        ),
    )
    for application in (best, middle, worst):
        await application.refresh_from_db()
        await Application.filter(id=application.id).update(
            hard_filter_result={
                "criteria": [
                    {"type": "schedule", "required": True, "passed": True},
                    {
                        "type": "location",
                        "required": False,
                        "passed": application.id == best.id,
                    },
                    {
                        "type": "experience",
                        "required": False,
                        "passed": application.id in (best.id, middle.id),
                    },
                ],
                "failed_questions": [],
            }
        )

    items = (await _candidates(client, vacancy)).json()["items"]
    order = [item["application_id"] for item in items]
    assert order == [best.id, middle.id, worst.id]

    best_card = items[0]
    assert sorted(best_card["explanation"]["matched"]) == ["location", "schedule"]
    assert best_card["explanation"]["experience"] == {
        "candidate": 24,
        "required": 12,
    }

    worst_card = items[-1]
    assert worst_card["explanation"]["matched"] == ["schedule"]
    assert worst_card["explanation"]["experience"] == {
        "candidate": 1,
        "required": 12,
    }


async def test_explanation_without_experience_criterion_is_none(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(
        employer, criteria=[(CriterionType.SCHEDULE, {"schedule": "full_time"}, True)]
    )
    application, _ = await _screened_application(client, vacancy, answers=[])
    await _relogin_employer(client, employer)

    card = (await _candidates(client, vacancy)).json()["items"][0]
    assert card["application_id"] == application.id
    assert card["explanation"]["experience"] is None


# --- Приглашение и взаимный интерес -------------------------------------------


async def test_invite_flow(client: AsyncClient) -> None:
    # 1. Приглашение переводит отклик во взаимный интерес и создаёт match
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    application = await _application(vacancy, await _candidate())

    response = await _decide(client, application, action="invited")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.MUTUAL_INTEREST.value
    assert body["action"] == DecisionAction.INVITED.value
    assert body["reject_reason"] is None

    await application.refresh_from_db()
    assert application.status == ApplicationStatus.MUTUAL_INTEREST

    decision = await EmployerDecision.get(application_id=application.id)
    assert decision.action == DecisionAction.INVITED
    assert decision.reject_reason is None

    match = await Match.get(application_id=application.id)
    assert body["match_id"] == match.id

    # 2. Аналитика: приглашение и создание match пишутся раздельно (раздел 60)
    events = [
        event
        for event in await AnalyticsEvent.filter(user_id=employer.user_id).order_by("id")
        if event.event_name != "notification_sent"
    ]
    assert [event.event_name for event in events] == [
        "candidate_invited",
        "match_created",
    ]
    assert events[1].payload == {
        "match_id": match.id,
        "application_id": application.id,
        "vacancy_id": vacancy.id,
    }

    # 3. Повторное приглашение того же отклика отклоняется, match не дублируется
    repeated = await _decide(client, application, action="invited")
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "invalid_state_transition"
    assert await Match.filter(application_id=application.id).count() == 1

    # 4. Приглашённый кандидат виден в списке со статусом взаимного интереса
    listed = (await _candidates(client, vacancy)).json()
    assert listed["items"][0]["status"] == ApplicationStatus.MUTUAL_INTEREST.value

    # 5. Приглашение остаётся возможным, даже если кандидат потом меняет профиль
    other_vacancy = await _vacancy(
        employer,
        criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)],
        questions=[("Есть ли медкнижка?", ScreeningQuestionType.BOOLEAN)],
    )
    screened, _ = await _screened_application(client, other_vacancy, answers=[True])
    await client.patch("/api/candidate/profile", json={"city": "Казань"})
    await _relogin_employer(client, employer)

    late_invite = await _decide(client, screened, action="invited")
    assert late_invite.status_code == 200, late_invite.text
    assert late_invite.json()["status"] == ApplicationStatus.MUTUAL_INTEREST.value


# --- Отказ ----------------------------------------------------------------------


async def test_reject_flow(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    # 1. Отказ с причиной сохраняется, match не создаётся
    with_reason = await _application(vacancy, await _candidate())
    reason_response = await _decide(
        client, with_reason, action="rejected", reject_reason="salary"
    )
    assert reason_response.status_code == 200, reason_response.text
    assert reason_response.json()["status"] == ApplicationStatus.REJECTED.value
    assert reason_response.json()["match_id"] is None
    assert not await Match.filter(application_id=with_reason.id).exists()
    reason_decision = await EmployerDecision.get(application_id=with_reason.id)
    assert reason_decision.action == DecisionAction.REJECTED
    assert reason_decision.reject_reason.value == "salary"

    # 2. Причина отказа необязательна — раздел 20, P1 сделает её обязательной
    without_reason = await _application(vacancy, await _candidate())
    no_reason_response = await _decide(client, without_reason, action="rejected")
    assert no_reason_response.status_code == 200, no_reason_response.text
    no_reason_decision = await EmployerDecision.get(application_id=without_reason.id)
    assert no_reason_decision.reject_reason is None

    # 3. Неизвестный action и причина без отказа — ошибки валидации
    unknown_action_target = await _application(vacancy, await _candidate())
    unknown_action = await _decide(client, unknown_action_target, action="maybe")
    assert unknown_action.status_code == 422
    assert unknown_action.json()["error"]["code"] == "validation_error"

    reason_without_rejection_target = await _application(vacancy, await _candidate())
    reason_without_rejection = await _decide(
        client,
        reason_without_rejection_target,
        action="invited",
        reject_reason="salary",
    )
    assert reason_without_rejection.status_code == 422
    assert reason_without_rejection.json()["error"]["code"] == (
        "reject_reason_not_applicable"
    )

    unknown_reason_target = await _application(vacancy, await _candidate())
    unknown_reason = await _decide(
        client, unknown_reason_target, action="rejected", reject_reason="не понравился"
    )
    assert unknown_reason.status_code == 422

    # 4. Список отражает новый статус, аналитика хранит причину отказа
    listed = {
        item["application_id"]: item["status"]
        for item in (await _candidates(client, vacancy)).json()["items"]
    }
    assert listed[with_reason.id] == ApplicationStatus.REJECTED.value
    assert listed[without_reason.id] == ApplicationStatus.REJECTED.value

    rejection_events = await AnalyticsEvent.filter(
        user_id=employer.user_id, event_name="candidate_rejected"
    ).order_by("id")
    assert any(
        event.payload.get("reject_reason") == "salary" for event in rejection_events
    )


# --- Резерв (P1, раздел 20) -----------------------------------------------------


async def test_reserve_flow(
    client: AsyncClient, notifications: RecordingTransport
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    # 1. Резерв — промежуточное решение: сохраняется, кандидат уведомлён,
    # match не создаётся
    application = await _application(vacancy, await _candidate())
    reserved = await _decide(client, application, action="reserved")
    assert reserved.status_code == 200, reserved.text
    body = reserved.json()
    assert body["status"] == ApplicationStatus.RESERVED.value
    assert body["action"] == DecisionAction.RESERVED.value
    assert body["match_id"] is None
    assert not await Match.filter(application_id=application.id).exists()

    decision = await EmployerDecision.get(application_id=application.id)
    assert decision.action == DecisionAction.RESERVED

    candidate_texts = notifications.texts_for(application.candidate_id)
    assert len(candidate_texts) == 1
    assert vacancy.title in candidate_texts[0]

    reserve_events = await AnalyticsEvent.filter(
        user_id=employer.user_id, event_name="candidate_reserved"
    )
    assert len(reserve_events) == 1
    assert reserve_events[0].payload["application_id"] == application.id

    # 2. Резерв виден в списке кандидатов работодателя
    listed = {
        item["application_id"]: item["status"]
        for item in (await _candidates(client, vacancy)).json()["items"]
    }
    assert listed[application.id] == ApplicationStatus.RESERVED.value

    # 3. Из резерва можно позже пригласить — с созданием match, как обычно
    invited = await _decide(client, application, action="invited")
    assert invited.status_code == 200, invited.text
    assert invited.json()["status"] == ApplicationStatus.MUTUAL_INTEREST.value
    assert invited.json()["match_id"] is not None

    # 4. Повторное решение по уже приглашённому — недопустимый переход
    again = await _decide(client, application, action="rejected")
    assert again.status_code == 409

    # 5. Из резерва можно и отклонить
    reserved_then_rejected = await _application(vacancy, await _candidate())
    assert (
        await _decide(client, reserved_then_rejected, action="reserved")
    ).status_code == 200
    rejected = await _decide(
        client, reserved_then_rejected, action="rejected", reject_reason="other"
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == ApplicationStatus.REJECTED.value

    # 6. Из screening/hard_filter_failed в резерв нельзя — как и в любое
    # другое решение
    not_screened = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.SCREENING
    )
    blocked = await _decide(client, not_screened, action="reserved")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "invalid_state_transition"

    # 7. Дважды в резерв — тоже недопустимый переход
    twice = await _application(vacancy, await _candidate())
    assert (await _decide(client, twice, action="reserved")).status_code == 200
    assert (await _decide(client, twice, action="reserved")).status_code == 409


# --- Предусловия и права на решение --------------------------------------------


async def test_decision_preconditions_and_guards(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    # 1. Из screening решение принимать нельзя: отбор ещё не пройден
    in_screening = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.SCREENING
    )
    before_screening = await _decide(client, in_screening, action="invited")
    assert before_screening.status_code == 409
    assert before_screening.json()["error"]["code"] == "invalid_state_transition"
    assert before_screening.json()["error"]["details"] == {
        "status": ApplicationStatus.SCREENING.value,
        "target": ApplicationStatus.INVITED.value,
    }

    # 2. Провалившим обязательные фильтры — тоже нельзя
    failed_filter = await _application(
        vacancy, await _candidate(), status=ApplicationStatus.HARD_FILTER_FAILED
    )
    assert (await _decide(client, failed_filter, action="invited")).status_code == 409

    # 3. Решение нельзя принять дважды
    twice = await _application(vacancy, await _candidate())
    assert (await _decide(client, twice, action="invited")).status_code == 200
    repeated = await _decide(client, twice, action="rejected")
    assert repeated.status_code == 409
    assert await EmployerDecision.filter(application_id=twice.id).count() == 1

    # 4. Match, возникший в обход приглашения, блокирует решение целиком
    conflicting = await _application(vacancy, await _candidate())
    await Match.create(application_id=conflicting.id)
    conflict = await _decide(client, conflicting, action="invited")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "match_already_exists"
    await conflicting.refresh_from_db()
    assert conflicting.status == ApplicationStatus.PASSED
    assert await EmployerDecision.filter(application_id=conflicting.id).count() == 0

    # 5. Без сессии решение недоступно
    unauthenticated_target = await _application(vacancy, await _candidate())
    async with _fresh_client() as guest:
        assert (
            await _decide(guest, unauthenticated_target, action="invited")
        ).status_code == 401

    # 6. Кандидату решение недоступно вовсе
    candidate_target_candidate = await _candidate()
    candidate_target = await _application(vacancy, candidate_target_candidate)
    async with _fresh_client() as as_candidate:
        await _login(as_candidate, candidate_target_candidate.user_id, UserRole.CANDIDATE)
        wrong_role = await _decide(as_candidate, candidate_target, action="invited")
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    # 7. Чужой отклик решить нельзя, и его статус не меняется
    foreign_owner = await _other_user(UserRole.EMPLOYER)
    foreign_vacancy = await _vacancy(foreign_owner)
    foreign_application = await _application(foreign_vacancy, await _candidate())
    foreign = await _decide(client, foreign_application, action="invited")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "application_not_found"
    await foreign_application.refresh_from_db()
    assert foreign_application.status == ApplicationStatus.PASSED

    # 8. Несуществующий отклик — 404
    unknown = await client.post(
        "/api/applications/999999/decision", json={"action": "invited"}
    )
    assert unknown.status_code == 404


# --- Конкурентность и гонки состояния (диагностика важнее компактности) -------


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
    assert await Match.filter(application_id=application.id).count() == 1
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.MUTUAL_INTEREST


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
