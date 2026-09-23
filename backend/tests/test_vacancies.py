"""Создание, чтение, изменение и публикация вакансии.

`POST /api/vacancies`, `GET /api/vacancies/{id}`, `PATCH /api/vacancies/{id}`,
`GET /api/employer/vacancies`. Разделы 15, 16, 18, 27, 28, 29, 57 тех-доки.
"""

from datetime import date
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications.models import Application, ScreeningAnswer
from app.candidates.models import CandidateProfile
from app.core.config import settings
from app.core.enums import ApplicationStatus, UserRole, VacancyStatus
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(800000)
_candidate_ids = count(801000)

FITTING_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": date(2026, 10, 1),
}

FULL_VACANCY: dict[str, Any] = {
    "title": "Бариста в центре",
    "location": "Москва",
    "salary_min": "60000",
    "salary_max": "90000",
    "schedule": "full_time",
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Вакансии модуля не должны попадать в ленту соседних тестов."""
    yield
    await Vacancy.filter(employer_id__gte=800000, employer_id__lt=801000).delete()


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


async def _other_employer() -> User:
    return await User.create(
        user_id=next(_employer_ids), first_name="Другой", role=UserRole.EMPLOYER
    )


async def _candidate(client: AsyncClient) -> User:
    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await CandidateProfile.create(user_id=candidate.user_id, **FITTING_PROFILE)
    return candidate


async def _create(client: AsyncClient, **payload):
    return await client.post("/api/vacancies", json=payload)


async def _update(client: AsyncClient, vacancy_id: int, **payload):
    return await client.patch(f"/api/vacancies/{vacancy_id}", json=payload)


async def _created_vacancy(client: AsyncClient, **overrides) -> dict[str, Any]:
    response = await _create(client, **(FULL_VACANCY | overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --- Создание ---------------------------------------------------------------


async def test_creation_requires_session(client: AsyncClient) -> None:
    assert (await _create(client, **FULL_VACANCY)).status_code == 401


async def test_candidate_cannot_create_vacancy(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _create(client, **FULL_VACANCY)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_user_without_role_cannot_create_vacancy(client: AsyncClient) -> None:
    user_id = next(_employer_ids)
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )

    response = await _create(client, **FULL_VACANCY)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_selected"


async def test_vacancy_is_created_as_draft(client: AsyncClient) -> None:
    employer = await _employer(client)

    body = await _created_vacancy(client)

    assert body["status"] == VacancyStatus.DRAFT.value
    # Работодатель берётся из сессии, а не из тела запроса
    assert body["employer_id"] == employer.user_id
    assert body["title"] == "Бариста в центре"
    assert body["salary_min"] == "60000.00"
    assert body["salary_max"] == "90000.00"
    # Токен публичной ссылки выдаётся только при публикации (раздел 15)
    assert body["public_token"] is None
    assert body["public_url"] is None
    assert body["applications_count"] == 0

    vacancy = await Vacancy.get(id=body["id"])
    assert vacancy.employer_id == employer.user_id
    assert vacancy.status is VacancyStatus.DRAFT


async def test_criteria_and_questions_are_saved(client: AsyncClient) -> None:
    await _employer(client)

    body = await _created_vacancy(
        client,
        criteria=[
            {"type": "location", "required": True, "value": {"city": "Москва"}},
            {
                "type": "experience",
                "required": False,
                "value": {"min_months": 12},
                "weight": "0.80",
            },
        ],
        questions=[
            {
                "question": "Есть ли действующая медкнижка?",
                "type": "boolean",
                "required": True,
                "validation_rules": {"must_equal": True},
            },
            {"question": "Сколько лет опыта?", "type": "number", "required": True},
        ],
    )

    assert [item["type"] for item in body["criteria"]] == ["location", "experience"]
    assert body["criteria"][1]["weight"] == "0.80"
    # Порядок вопросов задаёт список, а не поле в теле запроса
    assert [item["sort_order"] for item in body["questions"]] == [1, 2]
    assert body["questions"][0]["validation_rules"] == {"must_equal": True}

    assert await VacancyCriterion.filter(vacancy_id=body["id"]).count() == 2
    assert await ScreeningQuestion.filter(vacancy_id=body["id"]).count() == 2


async def test_vacancy_can_be_published_on_creation(client: AsyncClient) -> None:
    employer = await _employer(client)

    body = await _created_vacancy(client, status="published")

    assert body["status"] == VacancyStatus.PUBLISHED.value
    assert body["public_token"]
    assert body["public_url"] == (
        f"{settings.app_url.rstrip('/')}/v/{body['public_token']}"
    )

    events = await AnalyticsEvent.filter(user_id=employer.user_id).order_by("id")
    assert [event.event_name for event in events] == [
        "vacancy_created",
        "vacancy_published",
    ]


async def test_incomplete_vacancy_is_not_published(client: AsyncClient) -> None:
    """Раздел 29: без обязательных данных публикации нет."""
    employer = await _employer(client)

    response = await _create(client, title="Бариста", status="published")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "vacancy_incomplete"
    assert response.json()["error"]["details"]["missing"] == [
        "location",
        "salary",
        "schedule",
    ]
    # Неполная вакансия не создаётся даже черновиком: запрос отклонён целиком
    assert not await Vacancy.filter(employer_id=employer.user_id).exists()


async def test_salary_min_only_is_enough_for_publication(client: AsyncClient) -> None:
    await _employer(client)

    body = await _created_vacancy(client, salary_max=None, status="published")

    assert body["status"] == VacancyStatus.PUBLISHED.value


async def test_invalid_vacancy_fields_are_rejected(client: AsyncClient) -> None:
    await _employer(client)

    empty_title = await _create(client, **(FULL_VACANCY | {"title": "   "}))
    inverted_salary = await _create(
        client, **(FULL_VACANCY | {"salary_min": "90000", "salary_max": "60000"})
    )
    closed_on_create = await _create(client, **(FULL_VACANCY | {"status": "closed"}))

    assert empty_title.status_code == 422
    assert inverted_salary.status_code == 422
    assert closed_on_create.status_code == 422


# --- Проверка условий и вопросов --------------------------------------------


async def test_criterion_with_unknown_key_is_rejected(client: AsyncClient) -> None:
    """Опечатка в условии молча превратила бы фильтр в ничто."""
    await _employer(client)

    response = await _create(
        client,
        **FULL_VACANCY,
        criteria=[{"type": "location", "required": True, "value": {"cityy": "Москва"}}],
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "vacancy_criteria_invalid"
    assert error["details"][0]["index"] == 0
    assert error["details"][0]["code"] == "unknown_keys"


async def test_salary_criterion_without_limit_is_rejected(client: AsyncClient) -> None:
    """Потолок берётся из вакансии; без него условию нечего проверять."""
    await _employer(client)

    response = await _create(
        client,
        title="Бариста",
        location="Москва",
        schedule="full_time",
        criteria=[{"type": "salary", "required": True, "value": {}}],
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["code"] == "salary_limit_required"


async def test_salary_criterion_uses_vacancy_ceiling(client: AsyncClient) -> None:
    await _employer(client)

    body = await _created_vacancy(
        client, criteria=[{"type": "salary", "required": True, "value": {}}]
    )

    assert body["criteria"][0]["value"] == {}


async def test_malformed_criteria_values_are_rejected(client: AsyncClient) -> None:
    await _employer(client)
    cases = [
        ({"type": "experience", "required": True, "value": {"min_months": -1}}, "negative_number"),
        ({"type": "experience", "required": True, "value": {"min_months": "год"}}, "integer_expected"),
        ({"type": "available_from", "required": True, "value": {"date": "01.10.2026"}}, "date_expected"),
        ({"type": "certificate", "required": True, "value": {"name": "  "}}, "non_empty_string_expected"),
        ({"type": "location", "required": True, "value": {"cities": "Москва"}}, "list_expected"),
        ({"type": "schedule", "required": True, "value": {}}, "value_required"),
    ]

    for criterion, expected_code in cases:
        response = await _create(client, **FULL_VACANCY, criteria=[criterion])

        assert response.status_code == 422, criterion
        assert response.json()["error"]["details"][0]["code"] == expected_code, criterion


async def test_question_rules_are_validated(client: AsyncClient) -> None:
    await _employer(client)
    cases = [
        (
            {"question": "Смена?", "type": "choice", "required": True},
            "options_required",
        ),
        (
            {
                "question": "Смена?",
                "type": "choice",
                "required": True,
                "validation_rules": {"options": ["утро", "вечер"], "must_equal": "ночь"},
            },
            "must_equal_not_in_options",
        ),
        (
            {
                "question": "Медкнижка?",
                "type": "boolean",
                "required": False,
                "validation_rules": {"must_equal": True},
            },
            "must_equal_requires_required",
        ),
        (
            {
                "question": "Медкнижка?",
                "type": "boolean",
                "required": True,
                "validation_rules": {"must_equal": "да"},
            },
            "boolean_expected",
        ),
        (
            {
                "question": "Опыт в месяцах?",
                "type": "number",
                "required": True,
                "validation_rules": {"min": 10, "max": 5},
            },
            "range_inverted",
        ),
        (
            {
                "question": "Расскажите о себе",
                "type": "text",
                "required": True,
                "validation_rules": {"options": ["да"]},
            },
            "rules_not_applicable",
        ),
    ]

    for question, expected_code in cases:
        response = await _create(client, **FULL_VACANCY, questions=[question])

        assert response.status_code == 422, question
        error = response.json()["error"]
        assert error["code"] == "screening_questions_invalid", question
        assert error["details"][0]["code"] == expected_code, question


async def test_too_many_questions_are_rejected(client: AsyncClient) -> None:
    """Раздел 18: в P0 3–4 вопроса, верхняя граница P1 — 6."""
    await _employer(client)

    response = await _create(
        client,
        **FULL_VACANCY,
        questions=[
            {"question": f"Вопрос {index}", "type": "text", "required": True}
            for index in range(7)
        ],
    )

    assert response.status_code == 422


# --- Чтение -----------------------------------------------------------------


async def test_owner_sees_own_draft_with_token_and_counters(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    created = await _created_vacancy(client, status="published")
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    await Application.create(
        vacancy_id=created["id"],
        candidate_id=candidate.user_id,
        status=ApplicationStatus.PASSED,
    )

    body = (await client.get(f"/api/vacancies/{created['id']}")).json()

    assert body["employer_id"] == employer.user_id
    assert body["public_token"] == created["public_token"]
    assert body["applications_count"] == 1


async def test_candidate_sees_published_vacancy_without_private_fields(
    client: AsyncClient,
) -> None:
    employer = await _other_employer()
    vacancy = await Vacancy.create(
        employer=employer, **FULL_VACANCY | {"salary_min": Decimal("60000"),
        "salary_max": Decimal("90000")}, status=VacancyStatus.PUBLISHED,
        public_token="token-for-candidate-test",
    )
    await ScreeningQuestion.create(
        vacancy=vacancy,
        question="Есть ли медкнижка?",
        type="boolean",
        required=True,
        sort_order=1,
        validation_rules={"must_equal": True},
    )
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    body = (await client.get(f"/api/vacancies/{vacancy.id}")).json()

    assert body["id"] == vacancy.id
    assert body["public_token"] is None
    assert body["public_url"] is None
    assert body["applications_count"] is None
    # Отсекающее условие кандидату не показывается
    assert body["questions"][0]["validation_rules"] == {}


async def test_candidate_does_not_see_draft(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await Vacancy.create(
        employer=employer, title="Черновик", status=VacancyStatus.DRAFT
    )
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await client.get(f"/api/vacancies/{vacancy.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_candidate_still_sees_closed_vacancy_of_own_application(
    client: AsyncClient,
) -> None:
    """Закрытая вакансия не должна исчезать из собственного отклика."""
    employer = await _other_employer()
    vacancy = await Vacancy.create(
        employer=employer, title="Закрытая", status=VacancyStatus.CLOSED
    )
    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await Application.create(
        vacancy_id=vacancy.id,
        candidate_id=candidate.user_id,
        status=ApplicationStatus.PASSED,
    )

    response = await client.get(f"/api/vacancies/{vacancy.id}")

    assert response.status_code == 200
    assert response.json()["id"] == vacancy.id


async def test_foreign_vacancy_is_not_visible_to_employer(
    client: AsyncClient,
) -> None:
    other = await _other_employer()
    vacancy = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.PUBLISHED
    )
    await _employer(client)

    response = await client.get(f"/api/vacancies/{vacancy.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_unknown_vacancy_returns_404(client: AsyncClient) -> None:
    await _employer(client)

    assert (await client.get("/api/vacancies/999999")).status_code == 404


# --- Изменение и публикация -------------------------------------------------


async def test_fields_are_updated(client: AsyncClient) -> None:
    await _employer(client)
    created = await _created_vacancy(client)

    response = await _update(
        client, created["id"], title="Бариста на Патриках", schedule="shift"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Бариста на Патриках"
    assert body["schedule"] == "shift"
    # Не переданные поля не меняются
    assert body["location"] == "Москва"


async def test_publication_through_patch_issues_token(client: AsyncClient) -> None:
    employer = await _employer(client)
    created = await _created_vacancy(client)

    body = (await _update(client, created["id"], status="published")).json()

    assert body["status"] == VacancyStatus.PUBLISHED.value
    assert body["public_token"]
    assert await AnalyticsEvent.filter(
        user_id=employer.user_id, event_name="vacancy_published"
    ).exists()


async def test_incomplete_vacancy_cannot_be_published_by_patch(
    client: AsyncClient,
) -> None:
    await _employer(client)
    created = await _created_vacancy(client, location=None, schedule=None)

    response = await _update(client, created["id"], status="published")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "vacancy_incomplete"
    assert (await Vacancy.get(id=created["id"])).status is VacancyStatus.DRAFT


async def test_republishing_keeps_public_token(client: AsyncClient) -> None:
    """Раздел 15: токен выдаётся один раз, разосланная ссылка не ломается."""
    await _employer(client)
    created = await _created_vacancy(client, status="published")
    token = created["public_token"]

    closed = await _update(client, created["id"], status="closed")
    reopened = await _update(client, created["id"], status="published")

    assert closed.json()["status"] == VacancyStatus.CLOSED.value
    assert closed.json()["public_token"] == token
    assert reopened.json()["public_token"] == token


async def test_published_vacancy_cannot_return_to_draft(client: AsyncClient) -> None:
    await _employer(client)
    created = await _created_vacancy(client, status="published")

    response = await _update(client, created["id"], status="draft")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_vacancy_status_transition"
    assert response.json()["error"]["details"] == {
        "status": "published",
        "target": "draft",
    }


async def test_same_status_is_not_an_error(client: AsyncClient) -> None:
    await _employer(client)
    created = await _created_vacancy(client)

    assert (await _update(client, created["id"], status="draft")).status_code == 200


async def test_criteria_are_replaced_entirely(client: AsyncClient) -> None:
    await _employer(client)
    created = await _created_vacancy(
        client,
        criteria=[{"type": "location", "required": True, "value": {"city": "Москва"}}],
    )

    body = (
        await _update(
            client,
            created["id"],
            criteria=[
                {"type": "schedule", "required": True, "value": {"schedule": "shift"}}
            ],
        )
    ).json()

    assert [item["type"] for item in body["criteria"]] == ["schedule"]
    assert await VacancyCriterion.filter(vacancy_id=created["id"]).count() == 1


async def test_questions_cannot_be_replaced_after_applications(
    client: AsyncClient,
) -> None:
    """Раздел 83: исторические ответы отклика удалять нельзя."""
    await _employer(client)
    created = await _created_vacancy(
        client,
        status="published",
        questions=[{"question": "Медкнижка?", "type": "boolean", "required": True}],
    )
    question = await ScreeningQuestion.get(vacancy_id=created["id"])
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    application = await Application.create(
        vacancy_id=created["id"],
        candidate_id=candidate.user_id,
        status=ApplicationStatus.PASSED,
    )
    await ScreeningAnswer.create(
        application_id=application.id, question_id=question.id, value={"value": True}
    )

    response = await _update(
        client,
        created["id"],
        questions=[{"question": "Другой вопрос", "type": "text", "required": True}],
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vacancy_has_applications"
    assert await ScreeningAnswer.filter(application_id=application.id).count() == 1
    assert await ScreeningQuestion.filter(id=question.id).exists()


async def test_questions_are_replaced_without_applications(
    client: AsyncClient,
) -> None:
    await _employer(client)
    created = await _created_vacancy(
        client,
        questions=[{"question": "Медкнижка?", "type": "boolean", "required": True}],
    )

    body = (
        await _update(
            client,
            created["id"],
            questions=[
                {"question": "Опыт в месяцах?", "type": "number", "required": True},
                {"question": "Готовы к сменам?", "type": "boolean", "required": True},
            ],
        )
    ).json()

    assert [item["question"] for item in body["questions"]] == [
        "Опыт в месяцах?",
        "Готовы к сменам?",
    ]
    assert [item["sort_order"] for item in body["questions"]] == [1, 2]


async def test_salary_range_is_checked_against_stored_value(
    client: AsyncClient,
) -> None:
    await _employer(client)
    created = await _created_vacancy(client)

    response = await _update(client, created["id"], salary_min="120000")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "salary_range_invalid"


async def test_empty_patch_changes_nothing(client: AsyncClient) -> None:
    await _employer(client)
    created = await _created_vacancy(client)

    body = (await _update(client, created["id"])).json()

    assert body["title"] == created["title"]
    assert body["status"] == created["status"]


async def test_foreign_vacancy_cannot_be_updated(client: AsyncClient) -> None:
    other = await _other_employer()
    vacancy = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.DRAFT
    )
    await _employer(client)

    response = await _update(client, vacancy.id, title="Перехвачено")

    assert response.status_code == 404
    await vacancy.refresh_from_db()
    assert vacancy.title == "Чужая"


async def test_candidate_cannot_update_vacancy(client: AsyncClient) -> None:
    other = await _other_employer()
    vacancy = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.PUBLISHED
    )
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _update(client, vacancy.id, title="Перехвачено")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


# --- Список кабинета --------------------------------------------------------


async def test_employer_list_shows_only_own_vacancies(client: AsyncClient) -> None:
    other = await _other_employer()
    await Vacancy.create(employer=other, title="Чужая", status=VacancyStatus.PUBLISHED)
    await _employer(client)
    first = await _created_vacancy(client, title="Первая")
    second = await _created_vacancy(client, title="Вторая")

    body = (await client.get("/api/employer/vacancies")).json()

    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
    assert all(item["applications_count"] == 0 for item in body["items"])


async def test_employer_list_pagination(client: AsyncClient) -> None:
    await _employer(client)
    for index in range(3):
        await _created_vacancy(client, title=f"Вакансия {index}")

    first = (await client.get("/api/employer/vacancies?limit=2&offset=0")).json()
    second = (await client.get("/api/employer/vacancies?limit=2&offset=2")).json()

    assert first["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )


async def test_employer_list_requires_employer_role(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await client.get("/api/employer/vacancies")

    assert response.status_code == 403


# --- Связка с лентой и откликом ---------------------------------------------


async def test_published_vacancy_reaches_feed_and_accepts_application(
    client: AsyncClient,
) -> None:
    """Созданная вакансия работает в подборе теми условиями, что заданы."""
    await _employer(client)
    fitting = await _created_vacancy(
        client,
        status="published",
        criteria=[
            {"type": "location", "required": True, "value": {"city": "Москва"}},
            {"type": "experience", "required": True, "value": {"min_months": 12}},
        ],
        questions=[
            {
                "question": "Есть ли медкнижка?",
                "type": "boolean",
                "required": True,
                "validation_rules": {"must_equal": True},
            }
        ],
    )
    unfitting = await _created_vacancy(
        client,
        title="Бариста в Казани",
        status="published",
        criteria=[{"type": "location", "required": True, "value": {"city": "Казань"}}],
    )

    await _candidate(client)
    feed = (await client.get("/api/vacancies/feed")).json()
    feed_ids = [item["id"] for item in feed["items"]]
    assert fitting["id"] in feed_ids
    assert unfitting["id"] not in feed_ids

    applied = await client.post(f"/api/vacancies/{fitting['id']}/apply")
    assert applied.status_code == 201, applied.text
    application_id = applied.json()["id"]

    question = await ScreeningQuestion.get(vacancy_id=fitting["id"])
    screening = await client.post(
        f"/api/applications/{application_id}/screening",
        json={"answers": [{"question_id": question.id, "value": True}]},
    )

    assert screening.status_code == 200, screening.text
    assert screening.json()["status"] == ApplicationStatus.PASSED.value


async def test_closed_vacancy_does_not_accept_applications(
    client: AsyncClient,
) -> None:
    await _employer(client)
    created = await _created_vacancy(client, status="published")
    assert (await _update(client, created["id"], status="closed")).status_code == 200

    await _candidate(client)
    response = await client.post(f"/api/vacancies/{created['id']}/apply")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vacancy_not_published"
