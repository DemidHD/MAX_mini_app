"""GET/POST /api/applications/{id}/screening. Разделы 18, 19, 26, 33, 59 тех-доки.

Guard'ы, happy path и взаимодействие с критериями вакансии собраны в
сквозные сценарии по одной функции на группу. Матрица валидации ответов
осталась табличной (`pytest.mark.parametrize`) — это тот же принцип
компактности, только выраженный через параметризацию, а не через merge.
Идемпотентность и конкурентность оставлены отдельными тестами: там важна
изолированная диагностика гонки, а не компактность.
"""

import asyncio
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest
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


# --- Доступ и чтение вопросов -------------------------------------------------


async def test_screening_access_guards_and_question_reading(
    client: AsyncClient,
) -> None:
    # 1. Без сессии ни читать, ни отправлять отбор нельзя
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

    # 2. Работодателю отбор недоступен
    stranger = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    employer_target = await _application(vacancy, stranger)
    await _login(client, next(_candidate_ids), role=UserRole.EMPLOYER)
    wrong_role = await client.get(
        f"/api/applications/{employer_target.id}/screening"
    )
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    # 3. Чужой отклик — 404: существование чужих откликов не раскрывается
    other = await User.create(
        user_id=next(_candidate_ids), first_name="Чужой", role=UserRole.CANDIDATE
    )
    foreign_application = await _application(vacancy, other)
    await _candidate(client)
    foreign = await client.get(f"/api/applications/{foreign_application.id}/screening")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "application_not_found"

    # 4. Несуществующий отклик — тоже 404
    assert (
        await client.get("/api/applications/999999/screening")
    ).status_code == 404

    # 5. Вопросы отдаются по порядку, отсекающие условия скрыты от кандидата
    own_candidate = await _candidate(client)
    own_application = await _application(vacancy, own_candidate)
    body = (
        await client.get(f"/api/applications/{own_application.id}/screening")
    ).json()
    assert body["application_id"] == own_application.id
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
    rules = {question["type"]: question["rules"] for question in body["questions"]}
    assert rules["boolean"] == {}
    assert rules["number"] == {"min": 0, "max": 600}
    assert rules["choice"] == {"options": ["full_time", "part_time"]}
    assert rules["text"] == {"max_length": 200}
    assert "must_equal" not in str(body)


# --- Happy path и обязательные фильтры -----------------------------------------


async def test_screening_happy_path_and_hard_filters(client: AsyncClient) -> None:
    # 1. Успешный отбор сохраняет все ответы и переводит отклик в passed
    vacancy = await _vacancy()
    candidate = await _candidate(client)
    application = await _application(vacancy, candidate)
    questions = await _question_ids(vacancy)
    passed = await client.post(
        f"/api/applications/{application.id}/screening",
        json=_answers(questions, FITTING_ANSWERS),
    )
    assert passed.status_code == 200, passed.text
    passed_body = passed.json()
    assert passed_body["status"] == ApplicationStatus.PASSED.value
    assert passed_body["failed_criteria"] == []
    assert passed_body["failed_questions"] == []
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

    # 2. Раздел 32 переводит отклик в screening сразу, но created тоже принимаем
    no_questions_vacancy = await _vacancy(questions=[])
    created_status_application = await _application(
        no_questions_vacancy, await _candidate(client), status=ApplicationStatus.CREATED
    )
    from_created = await client.post(
        f"/api/applications/{created_status_application.id}/screening",
        json={"answers": []},
    )
    assert from_created.status_code == 200, from_created.text
    assert from_created.json()["status"] == ApplicationStatus.PASSED.value

    # 3. Вакансия без вопросов проходит отбор без сохранённых ответов
    no_questions_application = await _application(
        no_questions_vacancy, await _candidate(client)
    )
    no_questions_response = await client.post(
        f"/api/applications/{no_questions_application.id}/screening",
        json={"answers": []},
    )
    assert no_questions_response.status_code == 200, no_questions_response.text
    assert no_questions_response.json()["status"] == ApplicationStatus.PASSED.value
    assert (
        await ScreeningAnswer.filter(application_id=no_questions_application.id).count()
    ) == 0

    # 4. Корректный, но не прошедший условие ответ — hard_filter_failed, а не 422
    cut_off_application = await _application(vacancy, await _candidate(client))
    cut_off = await client.post(
        f"/api/applications/{cut_off_application.id}/screening",
        json=_answers(questions, [False, 24, "full_time", None]),
    )
    assert cut_off.status_code == 200, cut_off.text
    cut_off_body = cut_off.json()
    assert cut_off_body["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
    assert cut_off_body["failed_questions"] == [questions[0].id]
    assert cut_off_body["failed_criteria"] == []
    await cut_off_application.refresh_from_db()
    assert cut_off_application.status == ApplicationStatus.HARD_FILTER_FAILED
    # Ответы сохраняются и при отказе: это история отклика
    assert (
        await ScreeningAnswer.filter(application_id=cut_off_application.id).count()
    ) == 3

    # 5. Обязательный критерий вакансии тоже проваливает отбор
    required_criterion_vacancy = await _vacancy(
        criteria=[(CriterionType.SCHEDULE, {"schedule": "night"}, True)]
    )
    required_application = await _application(
        required_criterion_vacancy, await _candidate(client)
    )
    required_questions = await _question_ids(required_criterion_vacancy)
    required_failed = await client.post(
        f"/api/applications/{required_application.id}/screening",
        json=_answers(required_questions, FITTING_ANSWERS),
    )
    assert required_failed.status_code == 200, required_failed.text
    required_body = required_failed.json()
    assert required_body["status"] == ApplicationStatus.HARD_FILTER_FAILED.value
    assert required_body["failed_criteria"] == [CriterionType.SCHEDULE.value]
    assert required_body["failed_questions"] == []

    # 6. Необязательный критерий отбор не проваливает
    optional_criterion_vacancy = await _vacancy(
        criteria=[(CriterionType.SCHEDULE, {"schedule": "night"}, False)]
    )
    optional_application = await _application(
        optional_criterion_vacancy, await _candidate(client)
    )
    optional_questions = await _question_ids(optional_criterion_vacancy)
    optional_response = await client.post(
        f"/api/applications/{optional_application.id}/screening",
        json=_answers(optional_questions, FITTING_ANSWERS),
    )
    assert optional_response.json()["status"] == ApplicationStatus.PASSED.value

    # 7. Нет данных в профиле — критерий не проверяется, как и в ленте
    uncheckable_vacancy = await _vacancy(
        criteria=[(CriterionType.EXPERIENCE, {"min_months": 120}, True)]
    )
    uncheckable_candidate = await _candidate(
        client, profile=FITTING_PROFILE | {"experience_months": None}
    )
    uncheckable_application = await _application(uncheckable_vacancy, uncheckable_candidate)
    uncheckable_questions = await _question_ids(uncheckable_vacancy)
    uncheckable_response = await client.post(
        f"/api/applications/{uncheckable_application.id}/screening",
        json=_answers(uncheckable_questions, FITTING_ANSWERS),
    )
    assert uncheckable_response.json()["status"] == ApplicationStatus.PASSED.value

    # 8. Сертификат не хранится в профиле: обязательный критерий закрывает ответ
    certificate_vacancy = await _vacancy(
        criteria=[(CriterionType.CERTIFICATE, {"name": "медкнижка"}, True)],
        questions=[CERTIFICATE_QUESTION],
    )
    certificate_application = await _application(
        certificate_vacancy, await _candidate(client)
    )
    certificate_questions = await _question_ids(certificate_vacancy)
    certificate_response = await client.post(
        f"/api/applications/{certificate_application.id}/screening",
        json=_answers(certificate_questions, [True]),
    )
    assert certificate_response.status_code == 200, certificate_response.text
    assert certificate_response.json()["status"] == ApplicationStatus.PASSED.value
    assert certificate_response.json()["failed_criteria"] == []

    # 9. Без профиля критерии проверять нечем — отбор идёт только по ответам
    no_profile_vacancy = await _vacancy(
        criteria=[(CriterionType.LOCATION, {"city": "Казань"}, True)],
        questions=[CERTIFICATE_QUESTION],
    )
    no_profile_candidate = await _login(client, next(_candidate_ids))
    no_profile_application = await _application(no_profile_vacancy, no_profile_candidate)
    no_profile_questions = await _question_ids(no_profile_vacancy)
    no_profile_response = await client.post(
        f"/api/applications/{no_profile_application.id}/screening",
        json=_answers(no_profile_questions, [True]),
    )
    assert no_profile_response.status_code == 200, no_profile_response.text
    assert no_profile_response.json()["status"] == ApplicationStatus.PASSED.value

    # 10. Раздел 57 запрещает новые отклики, а не завершение уже начатого отбора
    closed_vacancy = await _vacancy(status=VacancyStatus.CLOSED, questions=[])
    closed_application = await _application(closed_vacancy, await _candidate(client))
    closed_response = await client.post(
        f"/api/applications/{closed_application.id}/screening", json={"answers": []}
    )
    assert closed_response.status_code == 200, closed_response.text
    assert closed_response.json()["status"] == ApplicationStatus.PASSED.value


# --- Валидация ответов: табличная матрица --------------------------------------

INVALID_ANSWER_CASES = [
    pytest.param(2, [True, 24], ["answer_required"], id="missing_required_answer"),
    pytest.param(
        4, ["да", 24, "full_time", None], ["boolean_expected"], id="wrong_boolean_type"
    ),
    pytest.param(
        4,
        [True, True, "full_time", None],
        ["number_expected"],
        id="boolean_not_accepted_as_number",
    ),
    pytest.param(
        4, [True, 900, "full_time", None], ["number_too_large"], id="number_out_of_range"
    ),
    pytest.param(
        4,
        [True, 24, "ночные смены", None],
        ["choice_not_allowed"],
        id="choice_outside_options",
    ),
    pytest.param(
        4,
        ["да", 900, "ночь", None],
        ["boolean_expected", "number_too_large", "choice_not_allowed"],
        id="all_broken_answers_reported_at_once",
    ),
]


@pytest.mark.parametrize("answer_count,values,expected_codes", INVALID_ANSWER_CASES)
async def test_invalid_answers_are_rejected_and_not_saved(
    client: AsyncClient,
    answer_count: int,
    values: list[Any],
    expected_codes: list[str],
) -> None:
    application, questions = await _prepare(client)

    response = await _submit(
        client, application, _answers(questions[:answer_count], values)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "screening_answers_invalid"
    assert _problem_codes(response) == expected_codes
    # Невалидная отправка не должна оставлять следов: ни статуса, ни ответов
    await application.refresh_from_db()
    assert application.status == ApplicationStatus.SCREENING
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 0


# --- Прочие граничные случаи ответов --------------------------------------------


async def test_screening_answer_edge_cases(client: AsyncClient) -> None:
    # 1. Число, переданное строкой, приводится к числу
    numeric_application, numeric_questions = await _prepare(client)
    numeric_as_string = await _submit(
        client, numeric_application, _answers(numeric_questions, [True, "24", "full_time", None])
    )
    assert numeric_as_string.status_code == 200, numeric_as_string.text
    saved_number = await ScreeningAnswer.get(
        application_id=numeric_application.id, question_id=numeric_questions[1].id
    )
    assert saved_number.value == {"value": 24}

    # 2. Необязательный вопрос можно пропустить
    skip_application, skip_questions = await _prepare(client)
    skipped = await _submit(
        client, skip_application, _answers(skip_questions[:3], [True, 24, "full_time"])
    )
    assert skipped.status_code == 200, skipped.text
    assert await ScreeningAnswer.filter(application_id=skip_application.id).count() == 3

    # 3. Пустое поле формы — это отсутствие ответа, а не ошибка
    blank_application, blank_questions = await _prepare(client)
    blank = await _submit(
        client, blank_application, _answers(blank_questions, [True, 24, "full_time", "   "])
    )
    assert blank.status_code == 200, blank.text
    assert await ScreeningAnswer.filter(application_id=blank_application.id).count() == 3

    # 4. Слишком длинный текст отклоняется
    long_application, long_questions = await _prepare(client)
    too_long = await _submit(
        client, long_application, _answers(long_questions, [True, 24, "full_time", "я" * 201])
    )
    assert too_long.status_code == 422
    assert _problem_codes(too_long) == ["text_too_long"]

    # 5. Ответ на вопрос другой вакансии в чужой отклик не попадёт
    unknown_application, unknown_questions = await _prepare(client)
    unknown_payload = _answers(unknown_questions, FITTING_ANSWERS)
    unknown_payload["answers"].append({"question_id": 999999, "value": "любой"})
    unknown = await _submit(client, unknown_application, unknown_payload)
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_question"

    # 6. Два ответа на один вопрос не пройдут
    duplicate_application, duplicate_questions = await _prepare(client)
    duplicate_payload = _answers(duplicate_questions, FITTING_ANSWERS)
    duplicate_payload["answers"].append(
        {"question_id": duplicate_questions[0].id, "value": False}
    )
    duplicate = await _submit(client, duplicate_application, duplicate_payload)
    assert duplicate.status_code == 422
    assert duplicate.json()["error"]["code"] == "duplicate_answer"


# --- Идемпотентность и конкурентность (диагностика важнее компактности) -------


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


# --- Состояние после отбора, историчность, аналитика ---------------------------


async def test_screening_state_history_and_analytics(client: AsyncClient) -> None:
    # 1. Состояние после отбора отдаёт результат и сохранённые ответы
    application, questions = await _prepare(client)
    await _submit(client, application, _answers(questions, FITTING_ANSWERS))
    state = (
        await client.get(f"/api/applications/{application.id}/screening")
    ).json()
    assert state["status"] == ApplicationStatus.PASSED.value
    assert state["can_submit"] is False
    assert state["answers"] == [
        {"question_id": questions[0].id, "value": True},
        {"question_id": questions[1].id, "value": 24},
        {"question_id": questions[2].id, "value": "full_time"},
        {"question_id": questions[3].id, "value": "Готов выйти сразу"},
    ]

    # 2. Раздел 19: ответы отклика не переписываются при изменении профиля
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

    # 3. Раздел 60: воронка отбора должна попадать в analytics_events
    vacancy = await _vacancy()
    analytics_candidate = await _candidate(client)
    analytics_application = await _application(vacancy, analytics_candidate)
    analytics_questions = await _question_ids(vacancy)
    await _submit(
        client,
        analytics_application,
        _answers(analytics_questions, [False, 24, "full_time", None]),
    )
    events = await AnalyticsEvent.filter(user_id=analytics_candidate.user_id).order_by(
        "id"
    )
    assert [event.event_name for event in events] == [
        "screening_started",
        "screening_completed",
        "hard_filter_failed",
    ]
    assert events[-1].payload["failed_questions"] == [analytics_questions[0].id]
