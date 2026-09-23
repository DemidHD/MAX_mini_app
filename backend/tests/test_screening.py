"""GET/POST /api/applications/{id}/screening. Разделы 18, 19, 26, 33, 59 тех-доки."""

import asyncio
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
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

EMPLOYER_ID = 770000
_candidate_ids = count(770001)

# Профиль, подходящий вакансии из `_vacancy` по всем объективным критериям
FITTING_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": date(2026, 10, 1),
}

# Вопрос про медкнижку — тот самый обязательный `certificate`, который в P0
# нельзя проверить по профилю и подтверждают ответом (раздел 16)
CERTIFICATE_QUESTION = (
    "Есть ли действующая медкнижка?",
    ScreeningQuestionType.BOOLEAN,
    True,
    {"must_equal": True},
)
EXPERIENCE_QUESTION = (
    "Сколько месяцев вы работали по этой специальности?",
    ScreeningQuestionType.NUMBER,
    True,
    {"min": 0, "max": 600},
)
SCHEDULE_QUESTION = (
    "Какой график вам подходит?",
    ScreeningQuestionType.CHOICE,
    True,
    {"options": ["full_time", "part_time"]},
)
COMMENT_QUESTION = (
    "Что важно добавить?",
    ScreeningQuestionType.TEXT,
    False,
    {"max_length": 200},
)
DEFAULT_QUESTIONS = [
    CERTIFICATE_QUESTION,
    EXPERIENCE_QUESTION,
    SCHEDULE_QUESTION,
    COMMENT_QUESTION,
]


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Вакансии модуля не должны попадать в ленту и отборы соседних тестов."""
    yield
    await Vacancy.filter(employer_id=EMPLOYER_ID).delete()


async def _employer() -> User:
    employer = await User.get_or_none(user_id=EMPLOYER_ID)
    if employer is None:
        employer = await User.create(
            user_id=EMPLOYER_ID, first_name="Работодатель", role=UserRole.EMPLOYER
        )
    return employer


async def _vacancy(
    *,
    status: VacancyStatus = VacancyStatus.PUBLISHED,
    criteria: list[tuple[CriterionType, dict, bool]] | None = None,
    questions: list[tuple[str, ScreeningQuestionType, bool, dict | None]] | None = None,
    salary_max: Decimal | None = Decimal("90000"),
) -> Vacancy:
    vacancy = await Vacancy.create(
        employer=await _employer(),
        title="Бариста в центре",
        location="Москва",
        salary_max=salary_max,
        schedule="full_time",
        status=status,
    )
    for criterion_type, value, required in criteria or []:
        await VacancyCriterion.create(
            vacancy=vacancy, type=criterion_type, required=required, value=value
        )
    for order, (text, question_type, required, rules) in enumerate(
        DEFAULT_QUESTIONS if questions is None else questions, start=1
    ):
        await ScreeningQuestion.create(
            vacancy=vacancy,
            question=text,
            type=question_type,
            required=required,
            sort_order=order,
            validation_rules=rules,
        )
    return vacancy


async def _login(
    client: AsyncClient,
    user_id: int,
    *,
    role: UserRole | None = UserRole.CANDIDATE,
    profile: dict[str, Any] | None = None,
) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    if role is not None:
        await User.filter(user_id=user_id).update(role=role)
    if profile is not None:
        await CandidateProfile.create(user_id=user_id, **profile)
    return await User.get(user_id=user_id)


async def _candidate(
    client: AsyncClient, *, profile: dict[str, Any] | None = None
) -> User:
    """Кандидат с подходящим профилем, если не сказано иначе."""
    return await _login(
        client,
        next(_candidate_ids),
        profile=FITTING_PROFILE if profile is None else profile,
    )


async def _application(
    vacancy: Vacancy,
    candidate: User,
    *,
    status: ApplicationStatus = ApplicationStatus.SCREENING,
) -> Application:
    """Отклик создаётся напрямую: `POST /vacancies/:id/apply` — этап 3."""
    return await Application.create(
        vacancy=vacancy, candidate=candidate, status=status
    )


def _answers(questions: list[ScreeningQuestion], values: list[Any]) -> dict[str, Any]:
    return {
        "answers": [
            {"question_id": question.id, "value": value}
            for question, value in zip(questions, values, strict=True)
        ]
    }


async def _question_ids(vacancy: Vacancy) -> list[ScreeningQuestion]:
    return await ScreeningQuestion.filter(vacancy_id=vacancy.id).order_by("sort_order")


FITTING_ANSWERS = [True, 24, "full_time", "Готов выйти сразу"]


# --- Доступ -----------------------------------------------------------------


async def test_screening_requires_session(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    candidate = await _login(client, next(_candidate_ids), profile=FITTING_PROFILE)
    application = await _application(vacancy, candidate)
    client.cookies.clear()

    assert (
        await client.get(f"/api/applications/{application.id}/screening")
    ).status_code == 401
    assert (
        await client.post(
            f"/api/applications/{application.id}/screening", json={"answers": []}
        )
    ).status_code == 401


async def test_screening_requires_candidate_role(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    application = await _application(vacancy, candidate)
    await _login(client, next(_candidate_ids), role=UserRole.EMPLOYER)

    response = await client.get(f"/api/applications/{application.id}/screening")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_screening_of_foreign_application_is_not_visible(
    client: AsyncClient,
) -> None:
    """Чужой отклик — 404: существование чужих откликов наружу не раскрывается."""
    vacancy = await _vacancy()
    stranger = await User.create(
        user_id=next(_candidate_ids), first_name="Чужой", role=UserRole.CANDIDATE
    )
    application = await _application(vacancy, stranger)
    await _candidate(client)

    response = await client.get(f"/api/applications/{application.id}/screening")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "application_not_found"


async def test_unknown_application_returns_404(client: AsyncClient) -> None:
    await _candidate(client)

    response = await client.get("/api/applications/999999/screening")

    assert response.status_code == 404


# --- Чтение вопросов --------------------------------------------------------


async def test_questions_are_returned_in_order(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)

    response = await client.get(f"/api/applications/{application.id}/screening")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application_id"] == application.id
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == ApplicationStatus.SCREENING.value
    assert body["can_submit"] is True
    assert body["answers"] == []
    assert [question["sort_order"] for question in body["questions"]] == [1, 2, 3, 4]
    assert [question["type"] for question in body["questions"]] == [
        "boolean",
        "number",
        "choice",
        "text",
    ]


async def test_cut_off_condition_is_not_shown_to_candidate(
    client: AsyncClient,
) -> None:
    """`must_equal` кандидату не отдаётся: иначе ответ можно подогнать."""
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)

    body = (
        await client.get(f"/api/applications/{application.id}/screening")
    ).json()

    rules = {question["type"]: question["rules"] for question in body["questions"]}
    assert rules["boolean"] == {}
    assert rules["number"] == {"min": 0, "max": 600}
    assert rules["choice"] == {"options": ["full_time", "part_time"]}
    assert rules["text"] == {"max_length": 200}
    assert "must_equal" not in str(body)


# --- Основной путь ----------------------------------------------------------


async def test_screening_passes_and_saves_answers(client: AsyncClient) -> None:
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, FITTING_ANSWERS),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.PASSED.value
    assert body["failed_criteria"] == []
    assert body["failed_questions"] == []

    await application.refresh_from_db()
    assert application.status == ApplicationStatus.PASSED

    saved = await ScreeningAnswer.filter(application_id=application.id).order_by(
        "question_id"
    )
    assert [answer.value for answer in saved] == [
        {"value": True},
        {"value": 24},
        {"value": "full_time"},
        {"value": "Готов выйти сразу"},
    ]


async def test_application_in_created_status_can_pass_screening(
    client: AsyncClient,
) -> None:
    """Раздел 32 переводит отклик в `screening` сразу, но `created` тоже принимаем."""
    vacancy = await _vacancy(questions=[])
    candidate = await _candidate(client)
    application = await _application(
        vacancy, candidate, status=ApplicationStatus.CREATED
    )

    response = await client.post(
        f"/api/applications/{application.id}/screening", json={"answers": []}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.PASSED.value


async def test_vacancy_without_questions_passes_screening(
    client: AsyncClient,
) -> None:
    vacancy = await _vacancy(questions=[])
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)

    response = await client.post(
        f"/api/applications/{application.id}/screening", json={"answers": []}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.PASSED.value
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 0


# --- Hard filters -----------------------------------------------------------


async def test_answer_against_cut_off_condition_fails_screening(
    client: AsyncClient,
) -> None:
    """Корректный ответ, не прошедший условие, — это `hard_filter_failed`, а не 422."""
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, [False, 24, "full_time", None]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
    assert body["failed_questions"] == [questions[0].id]
    assert body["failed_criteria"] == []

    await application.refresh_from_db()
    assert application.status == ApplicationStatus.HARD_FILTER_FAILED
    # Ответы сохраняются и при отказе: это история отклика
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 3


async def test_required_vacancy_criterion_fails_screening(
    client: AsyncClient,
) -> None:
    vacancy = await _vacancy(
        criteria=[(CriterionType.SCHEDULE, {"schedule": "night"}, True)]
    )
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, FITTING_ANSWERS),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
    assert body["failed_criteria"] == [CriterionType.SCHEDULE.value]
    assert body["failed_questions"] == []


async def test_optional_criterion_does_not_fail_screening(
    client: AsyncClient,
) -> None:
    vacancy = await _vacancy(
        criteria=[(CriterionType.SCHEDULE, {"schedule": "night"}, False)]
    )
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, FITTING_ANSWERS),
    )

    assert response.json()["status"] == ApplicationStatus.PASSED.value


async def test_uncheckable_criterion_does_not_fail_screening(
    client: AsyncClient,
) -> None:
    """Нет данных в профиле — критерий не проверяется, как и в ленте."""
    vacancy = await _vacancy(
        criteria=[(CriterionType.EXPERIENCE, {"min_months": 120}, True)]
    )
    candidate = await _candidate(
        client, profile=FITTING_PROFILE | {"experience_months": None}
    )
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, FITTING_ANSWERS),
    )

    assert response.json()["status"] == ApplicationStatus.PASSED.value


async def test_certificate_criterion_is_confirmed_by_answer(
    client: AsyncClient,
) -> None:
    """Сертификат не хранится в профиле: обязательный критерий закрывает ответ."""
    vacancy = await _vacancy(
        criteria=[(CriterionType.CERTIFICATE, {"name": "медкнижка"}, True)],
        questions=[CERTIFICATE_QUESTION],
    )
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    passed = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, [True]),
    )

    assert passed.status_code == 200, passed.text
    assert passed.json()["status"] == ApplicationStatus.PASSED.value
    assert passed.json()["failed_criteria"] == []


async def test_screening_without_profile_is_not_blocked_by_criteria(
    client: AsyncClient,
) -> None:
    """Профиля нет — проверять критерии нечем; отбор идёт по ответам."""
    vacancy = await _vacancy(
        criteria=[(CriterionType.LOCATION, {"city": "Казань"}, True)],
        questions=[CERTIFICATE_QUESTION],
    )
    candidate = await _login(client, next(_candidate_ids))
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    response = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, [True]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.PASSED.value


async def test_closed_vacancy_does_not_block_screening(client: AsyncClient) -> None:
    """Раздел 57 запрещает новые отклики, а не завершение уже начатого отбора."""
    vacancy = await _vacancy(status=VacancyStatus.CLOSED, questions=[])
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)

    response = await client.post(
        f"/api/applications/{application.id}/screening", json={"answers": []}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == ApplicationStatus.PASSED.value


# --- Валидация ответов ------------------------------------------------------


async def _submit(
    client: AsyncClient, application: Application, payload: dict[str, Any]
):
    return await client.post(
        f"/api/applications/{application.id}/screening", json=payload
    )


async def _prepare(client: AsyncClient) -> tuple[Application, list[ScreeningQuestion]]:
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    return application, await _question_ids(vacancy)


def _problem_codes(response) -> list[str]:
    return [item["code"] for item in response.json()["error"]["details"]]


async def test_missing_required_answer_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions[:2], [True, 24])
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "screening_answers_invalid"
    assert _problem_codes(response) == ["answer_required"]
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.SCREENING
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 0


async def test_wrong_answer_type_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, ["да", 24, "full_time", None])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == ["boolean_expected"]


async def test_boolean_is_not_accepted_as_number(client: AsyncClient) -> None:
    """`True` — не единица: это ответ не того типа."""
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, True, "full_time", None])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == ["number_expected"]


async def test_number_as_string_is_accepted(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, "24", "full_time", None])
    )

    assert response.status_code == 200, response.text
    saved = await ScreeningAnswer.get(
        application_id=application.id, question_id=questions[1].id
    )
    assert saved.value == {"value": 24}


async def test_number_out_of_range_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, 900, "full_time", None])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == ["number_too_large"]


async def test_choice_outside_options_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, 24, "ночные смены", None])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == ["choice_not_allowed"]


async def test_all_broken_answers_are_reported_at_once(client: AsyncClient) -> None:
    """Frontend подсвечивает все поля за один запрос, а не по одному за попытку."""
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, ["да", 900, "ночь", None])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == [
        "boolean_expected",
        "number_too_large",
        "choice_not_allowed",
    ]


async def test_optional_question_can_be_skipped(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions[:3], [True, 24, "full_time"])
    )

    assert response.status_code == 200, response.text
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 3


async def test_blank_optional_answer_is_not_stored(client: AsyncClient) -> None:
    """Пустое поле формы — это отсутствие ответа, а не ошибка."""
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, 24, "full_time", "   "])
    )

    assert response.status_code == 200, response.text
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 3


async def test_too_long_text_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions, [True, 24, "full_time", "я" * 201])
    )

    assert response.status_code == 422
    assert _problem_codes(response) == ["text_too_long"]


async def test_unknown_question_is_rejected(client: AsyncClient) -> None:
    """Ответ на вопрос другой вакансии в чужой отклик не попадёт."""
    application, questions = await _prepare(client)
    payload = _answers(questions, FITTING_ANSWERS)
    payload["answers"].append({"question_id": 999999, "value": "любой"})

    response = await _submit(client, application, payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_question"


async def test_duplicate_answer_is_rejected(client: AsyncClient) -> None:
    application, questions = await _prepare(client)
    payload = _answers(questions, FITTING_ANSWERS)
    payload["answers"].append({"question_id": questions[0].id, "value": False})

    response = await _submit(client, application, payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "duplicate_answer"


# --- Повторная обработка ----------------------------------------------------


async def test_screening_cannot_be_passed_twice(client: AsyncClient) -> None:
    application, questions = await _prepare(client)
    payload = _answers(questions, FITTING_ANSWERS)
    assert (await _submit(client, application, payload)).status_code == 200

    repeated = await _submit(client, application, payload)

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "screening_already_completed"
    assert repeated.json()["error"]["details"] == {
        "status": ApplicationStatus.PASSED.value
    }
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 4


async def test_concurrent_screening_is_processed_once(client: AsyncClient) -> None:
    """Два одновременных запроса не должны задвоить ответы и пройти отбор дважды."""
    application, questions = await _prepare(client)
    payload = _answers(questions, FITTING_ANSWERS)

    responses = await asyncio.gather(
        *[_submit(client, application, payload) for _ in range(4)]
    )

    codes = sorted(response.status_code for response in responses)
    assert codes == [200, 409, 409, 409]
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 4


async def test_state_after_screening_shows_result(client: AsyncClient) -> None:
    application, questions = await _prepare(client)
    await _submit(client, application, _answers(questions, FITTING_ANSWERS))

    body = (
        await client.get(f"/api/applications/{application.id}/screening")
    ).json()

    assert body["status"] == ApplicationStatus.PASSED.value
    assert body["can_submit"] is False
    assert body["answers"] == [
        {"question_id": questions[0].id, "value": True},
        {"question_id": questions[1].id, "value": 24},
        {"question_id": questions[2].id, "value": "full_time"},
        {"question_id": questions[3].id, "value": "Готов выйти сразу"},
    ]


# --- Историчность и аналитика ----------------------------------------------


async def test_answers_survive_profile_change(client: AsyncClient) -> None:
    """Раздел 19: ответы отклика не переписываются при изменении профиля."""
    application, questions = await _prepare(client)
    await _submit(client, application, _answers(questions, FITTING_ANSWERS))

    changed = await client.patch(
        "/api/candidate/profile",
        json={"city": "Казань", "schedule": "part_time", "experience_months": 0},
    )
    assert changed.status_code == 200, changed.text

    await application.refresh_from_db()
    assert application.status == ApplicationStatus.PASSED
    saved = await ScreeningAnswer.filter(application_id=application.id).order_by(
        "question_id"
    )
    assert [answer.value["value"] for answer in saved] == FITTING_ANSWERS


async def test_screening_writes_analytics_events(client: AsyncClient) -> None:
    """Раздел 60: воронка отбора должна попадать в `analytics_events`."""
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)

    await _submit(
        client, application, _answers(questions, [False, 24, "full_time", None])
    )

    events = await AnalyticsEvent.filter(user_id=candidate.user_id).order_by("id")
    assert [event.event_name for event in events] == [
        "screening_started",
        "screening_completed",
        "hard_filter_failed",
    ]
    assert events[-1].payload["failed_questions"] == [questions[0].id]
