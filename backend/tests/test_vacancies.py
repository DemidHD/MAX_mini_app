"""Создание, чтение, изменение и публикация вакансии.

`POST /api/vacancies`, `GET /api/vacancies/{id}`, `PATCH /api/vacancies/{id}`,
`GET /api/employer/vacancies`. Разделы 15, 16, 18, 27, 28, 29, 57 тех-доки.

Тесты сгруппированы по сквозным сценариям (guard'ы и happy path одного
эндпоинта проверяются в одной функции подряд), а не по одному тесту на
каждый отдельный кейс. Отдельными тестами остаются только те проверки,
которым нужна независимая диагностика из-за тяжёлого/отличного состояния
(например, вопрос с уже сохранённым ответом отклика).
"""

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


# --- Создание: guard'ы и happy path ------------------------------------------


async def test_vacancy_creation_guards_and_happy_path(client: AsyncClient) -> None:
    # 1. Без сессии и без нужной роли создать вакансию нельзя
    assert (await _create(client, **FULL_VACANCY)).status_code == 401

    candidate_client_response = await _login(
        client, next(_candidate_ids), UserRole.CANDIDATE
    )
    del candidate_client_response
    wrong_role = await _create(client, **FULL_VACANCY)
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    roleless_id = next(_employer_ids)
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=roleless_id))},
    )
    no_role = await _create(client, **FULL_VACANCY)
    assert no_role.status_code == 403
    assert no_role.json()["error"]["code"] == "role_not_selected"

    # 2. Черновик создаётся работодателем из сессии, без токена публичной ссылки
    employer = await _employer(client)
    body = await _created_vacancy(client)
    assert body["status"] == VacancyStatus.DRAFT.value
    assert body["employer_id"] == employer.user_id
    assert body["title"] == "Бариста в центре"
    assert body["salary_min"] == "60000.00"
    assert body["salary_max"] == "90000.00"
    assert body["public_token"] is None
    assert body["public_url"] is None
    assert body["applications_count"] == 0
    vacancy = await Vacancy.get(id=body["id"])
    assert vacancy.employer_id == employer.user_id
    assert vacancy.status is VacancyStatus.DRAFT

    # 3. Условия и вопросы отбора сохраняются в заданном порядке
    with_criteria = await _created_vacancy(
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
    assert [item["type"] for item in with_criteria["criteria"]] == [
        "location",
        "experience",
    ]
    assert with_criteria["criteria"][1]["weight"] == "0.80"
    assert [item["sort_order"] for item in with_criteria["questions"]] == [1, 2]
    assert with_criteria["questions"][0]["validation_rules"] == {"must_equal": True}
    assert await VacancyCriterion.filter(vacancy_id=with_criteria["id"]).count() == 2
    assert await ScreeningQuestion.filter(vacancy_id=with_criteria["id"]).count() == 2

    # 4. Публикация сразу при создании выдаёт токен и пишет аналитику
    published = await _created_vacancy(client, status="published")
    assert published["status"] == VacancyStatus.PUBLISHED.value
    assert published["public_token"]
    assert published["public_url"] == (
        f"{settings.app_url.rstrip('/')}/v/{published['public_token']}"
    )
    events = await AnalyticsEvent.filter(user_id=employer.user_id).order_by("id")
    assert [event.event_name for event in events] == [
        "vacancy_created",
        "vacancy_created",
        "vacancy_created",
        "vacancy_published",
    ]

    # 5. Без обязательных данных публикация отклоняется, вакансия не создаётся вовсе
    incomplete = await _create(client, title="Бариста", status="published")
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "vacancy_incomplete"
    assert incomplete.json()["error"]["details"]["missing"] == [
        "location",
        "salary",
        "schedule",
    ]
    assert await Vacancy.filter(employer_id=employer.user_id).count() == 3

    # 6. Указан только нижний порог зарплаты — этого достаточно для публикации
    min_only = await _created_vacancy(client, salary_max=None, status="published")
    assert min_only["status"] == VacancyStatus.PUBLISHED.value

    # 7. Некорректные поля отклоняются каждый по своей причине
    empty_title = await _create(client, **(FULL_VACANCY | {"title": "   "}))
    inverted_salary = await _create(
        client, **(FULL_VACANCY | {"salary_min": "90000", "salary_max": "60000"})
    )
    closed_on_create = await _create(client, **(FULL_VACANCY | {"status": "closed"}))
    assert empty_title.status_code == 422
    assert inverted_salary.status_code == 422
    assert closed_on_create.status_code == 422


# --- Название заведения и описание (не из тех-доки, доп. поля вакансии) ------


async def test_vacancy_company_name_and_description(client: AsyncClient) -> None:
    await _employer(client)

    # 1. Сохраняются при создании, необязательны для публикации
    created = await _created_vacancy(
        client,
        company_name="Кофейня «Утро»",
        description="Ищем бариста в дружную команду.",
        status="published",
    )
    assert created["status"] == VacancyStatus.PUBLISHED.value
    assert created["company_name"] == "Кофейня «Утро»"
    assert created["description"] == "Ищем бариста в дружную команду."

    # 2. Без них вакансия по-прежнему публикуется (раздел 29 их не требует)
    without = await _created_vacancy(client, status="published")
    assert without["status"] == VacancyStatus.PUBLISHED.value
    assert without["company_name"] is None
    assert without["description"] is None

    # 3. Обновляются независимо от остальных полей
    updated = await _update(client, created["id"], company_name="Кофейня «Утро-2»")
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["company_name"] == "Кофейня «Утро-2»"
    assert body["description"] == "Ищем бариста в дружную команду."

    # 4. Пустая строка очищает поле, как location/schedule
    cleared = await _update(client, created["id"], description="   ")
    assert cleared.json()["description"] is None


# --- Лимит черновиков (не из тех-доки, продуктовое ограничение) --------------


async def test_vacancy_draft_limit(client: AsyncClient) -> None:
    await _employer(client)

    created_ids = []
    for _ in range(settings.vacancy_draft_limit):
        response = await _create(client, **FULL_VACANCY)
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    over_limit = await _create(client, **FULL_VACANCY)
    assert over_limit.status_code == 409
    assert over_limit.json()["error"]["code"] == "draft_limit_reached"
    assert over_limit.json()["error"]["details"] == {
        "limit": settings.vacancy_draft_limit
    }

    # Публикация одного черновика освобождает место для нового
    freed = await _update(client, created_ids[0], status="published")
    assert freed.status_code == 200, freed.text

    assert (await _create(client, **FULL_VACANCY)).status_code == 201
    # Лимит по-прежнему в силе для следующего черновика
    assert (await _create(client, **FULL_VACANCY)).status_code == 409

    # Публикация сразу при создании не расходует лимит черновиков
    for _ in range(3):
        assert (
            await _create(client, **FULL_VACANCY, status="published")
        ).status_code == 201


# --- Валидация условий и вопросов --------------------------------------------


async def test_vacancy_criteria_and_question_validation(client: AsyncClient) -> None:
    await _employer(client)

    # 1. Опечатка в ключе условия молча превратила бы фильтр в ничто
    unknown_key = await _create(
        client,
        **FULL_VACANCY,
        criteria=[{"type": "location", "required": True, "value": {"cityy": "Москва"}}],
    )
    assert unknown_key.status_code == 422
    error = unknown_key.json()["error"]
    assert error["code"] == "vacancy_criteria_invalid"
    assert error["details"][0]["index"] == 0
    assert error["details"][0]["code"] == "unknown_keys"

    # 2. Потолок зарплаты условия берётся из вакансии; без него условию нечего проверять
    no_limit = await _create(
        client,
        title="Бариста",
        location="Москва",
        schedule="full_time",
        criteria=[{"type": "salary", "required": True, "value": {}}],
    )
    assert no_limit.status_code == 422
    assert no_limit.json()["error"]["details"][0]["code"] == "salary_limit_required"

    with_ceiling = await _created_vacancy(
        client, criteria=[{"type": "salary", "required": True, "value": {}}]
    )
    assert with_ceiling["criteria"][0]["value"] == {}

    # 3. Каждый тип условия проверяет форму своего значения
    malformed_cases = [
        ({"type": "experience", "required": True, "value": {"min_months": -1}}, "negative_number"),
        ({"type": "experience", "required": True, "value": {"min_months": "год"}}, "integer_expected"),
        ({"type": "available_from", "required": True, "value": {"date": "01.10.2026"}}, "date_expected"),
        ({"type": "certificate", "required": True, "value": {"name": "  "}}, "non_empty_string_expected"),
        ({"type": "location", "required": True, "value": {"cities": "Москва"}}, "list_expected"),
        ({"type": "schedule", "required": True, "value": {}}, "value_required"),
    ]
    for criterion, expected_code in malformed_cases:
        response = await _create(client, **FULL_VACANCY, criteria=[criterion])
        assert response.status_code == 422, criterion
        assert response.json()["error"]["details"][0]["code"] == expected_code, criterion

    # 4. Правила валидации вопросов проверяются по типу вопроса
    question_cases = [
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
    for question, expected_code in question_cases:
        response = await _create(client, **FULL_VACANCY, questions=[question])
        assert response.status_code == 422, question
        error = response.json()["error"]
        assert error["code"] == "screening_questions_invalid", question
        assert error["details"][0]["code"] == expected_code, question

    # 5. Раздел 18: в P0 3–4 вопроса, верхняя граница P1 — 6
    too_many = await _create(
        client,
        **FULL_VACANCY,
        questions=[
            {"question": f"Вопрос {index}", "type": "text", "required": True}
            for index in range(7)
        ],
    )
    assert too_many.status_code == 422


# --- Чтение и видимость -------------------------------------------------------


async def test_vacancy_read_visibility(client: AsyncClient) -> None:
    # 1. Владелец видит свой черновик/публикацию с токеном и счётчиками
    employer = await _employer(client)
    created = await _created_vacancy(client, status="published")
    counted_candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    await Application.create(
        vacancy_id=created["id"],
        candidate_id=counted_candidate.user_id,
        status=ApplicationStatus.PASSED,
    )
    owner_view = (await client.get(f"/api/vacancies/{created['id']}")).json()
    assert owner_view["employer_id"] == employer.user_id
    assert owner_view["public_token"] == created["public_token"]
    assert owner_view["applications_count"] == 1

    # 2. Кандидат видит опубликованную вакансию без приватных полей
    other = await _other_employer()
    public_vacancy = await Vacancy.create(
        employer=other,
        **FULL_VACANCY
        | {"salary_min": Decimal("60000"), "salary_max": Decimal("90000")},
        status=VacancyStatus.PUBLISHED,
        public_token="token-for-candidate-test",
    )
    await ScreeningQuestion.create(
        vacancy=public_vacancy,
        question="Есть ли медкнижка?",
        type="boolean",
        required=True,
        sort_order=1,
        validation_rules={"must_equal": True},
    )
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    candidate_view = (await client.get(f"/api/vacancies/{public_vacancy.id}")).json()
    assert candidate_view["id"] == public_vacancy.id
    assert candidate_view["public_token"] is None
    assert candidate_view["public_url"] is None
    assert candidate_view["applications_count"] is None
    assert candidate_view["questions"][0]["validation_rules"] == {}

    # 3. Черновик кандидату не виден
    draft = await Vacancy.create(
        employer=other, title="Черновик", status=VacancyStatus.DRAFT
    )
    draft_response = await client.get(f"/api/vacancies/{draft.id}")
    assert draft_response.status_code == 404
    assert draft_response.json()["error"]["code"] == "vacancy_not_found"

    # 4. Закрытая вакансия не должна исчезать из собственного отклика кандидата
    closed = await Vacancy.create(
        employer=other, title="Закрытая", status=VacancyStatus.CLOSED
    )
    applicant = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await Application.create(
        vacancy_id=closed.id, candidate_id=applicant.user_id, status=ApplicationStatus.PASSED
    )
    closed_response = await client.get(f"/api/vacancies/{closed.id}")
    assert closed_response.status_code == 200
    assert closed_response.json()["id"] == closed.id

    # 5. Чужая вакансия не видна работодателю
    foreign = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.PUBLISHED
    )
    await _employer(client)
    foreign_response = await client.get(f"/api/vacancies/{foreign.id}")
    assert foreign_response.status_code == 404
    assert foreign_response.json()["error"]["code"] == "vacancy_not_found"

    # 6. Несуществующая вакансия — 404
    assert (await client.get("/api/vacancies/999999")).status_code == 404


# --- Изменение и публикация ---------------------------------------------------


async def test_vacancy_update_lifecycle(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Тест создаёт больше черновиков подряд, чем допускает продуктовый лимит
    # (не связанный с тем, что здесь проверяется) — раздвигаем его на время теста
    monkeypatch.setattr(settings, "vacancy_draft_limit", 100)
    employer = await _employer(client)

    # 1. Переданные поля меняются, остальные — нет
    created = await _created_vacancy(client)
    updated = await _update(
        client, created["id"], title="Бариста на Патриках", schedule="shift"
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["title"] == "Бариста на Патриках"
    assert updated_body["schedule"] == "shift"
    assert updated_body["location"] == "Москва"

    # 2. Публикация через PATCH выдаёт токен и пишет аналитику
    published = (await _update(client, created["id"], status="published")).json()
    assert published["status"] == VacancyStatus.PUBLISHED.value
    assert published["public_token"]
    assert await AnalyticsEvent.filter(
        user_id=employer.user_id, event_name="vacancy_published"
    ).exists()

    # 3. Неполную вакансию через PATCH тоже нельзя опубликовать
    incomplete = await _created_vacancy(client, location=None, schedule=None)
    incomplete_publish = await _update(client, incomplete["id"], status="published")
    assert incomplete_publish.status_code == 422
    assert incomplete_publish.json()["error"]["code"] == "vacancy_incomplete"
    assert (await Vacancy.get(id=incomplete["id"])).status is VacancyStatus.DRAFT

    # 4. Токен выдаётся один раз: закрытие и повторная публикация его не меняют
    token = published["public_token"]
    closed = await _update(client, created["id"], status="closed")
    reopened = await _update(client, created["id"], status="published")
    assert closed.json()["status"] == VacancyStatus.CLOSED.value
    assert closed.json()["public_token"] == token
    assert reopened.json()["public_token"] == token

    # 5. Из published нельзя вернуться в draft
    invalid_transition = await _update(client, created["id"], status="draft")
    assert invalid_transition.status_code == 409
    assert invalid_transition.json()["error"]["code"] == (
        "invalid_vacancy_status_transition"
    )
    assert invalid_transition.json()["error"]["details"] == {
        "status": "published",
        "target": "draft",
    }

    # 6. Тот же статус — не ошибка
    same_status_target = await _created_vacancy(client)
    assert (
        await _update(client, same_status_target["id"], status="draft")
    ).status_code == 200

    # 7. Условия заменяются целиком
    with_criteria = await _created_vacancy(
        client,
        criteria=[{"type": "location", "required": True, "value": {"city": "Москва"}}],
    )
    replaced = (
        await _update(
            client,
            with_criteria["id"],
            criteria=[
                {"type": "schedule", "required": True, "value": {"schedule": "shift"}}
            ],
        )
    ).json()
    assert [item["type"] for item in replaced["criteria"]] == ["schedule"]
    assert await VacancyCriterion.filter(vacancy_id=with_criteria["id"]).count() == 1

    # 8. Вопросы заменяются, пока по вакансии нет откликов
    with_questions = await _created_vacancy(
        client,
        questions=[{"question": "Медкнижка?", "type": "boolean", "required": True}],
    )
    replaced_questions = (
        await _update(
            client,
            with_questions["id"],
            questions=[
                {"question": "Опыт в месяцах?", "type": "number", "required": True},
                {"question": "Готовы к сменам?", "type": "boolean", "required": True},
            ],
        )
    ).json()
    assert [item["question"] for item in replaced_questions["questions"]] == [
        "Опыт в месяцах?",
        "Готовы к сменам?",
    ]
    assert [item["sort_order"] for item in replaced_questions["questions"]] == [1, 2]

    # 9. Диапазон зарплаты проверяется относительно уже сохранённого значения
    salary_target = await _created_vacancy(client)
    invalid_salary = await _update(client, salary_target["id"], salary_min="120000")
    assert invalid_salary.status_code == 422
    assert invalid_salary.json()["error"]["code"] == "salary_range_invalid"

    # 10. Пустой PATCH ничего не меняет
    unchanged_target = await _created_vacancy(client)
    unchanged = (await _update(client, unchanged_target["id"])).json()
    assert unchanged["title"] == unchanged_target["title"]
    assert unchanged["status"] == unchanged_target["status"]

    # 11. Чужую вакансию обновить нельзя
    other = await _other_employer()
    foreign_vacancy = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.DRAFT
    )
    foreign_update = await _update(client, foreign_vacancy.id, title="Перехвачено")
    assert foreign_update.status_code == 404
    await foreign_vacancy.refresh_from_db()
    assert foreign_vacancy.title == "Чужая"

    # 12. Кандидат не может обновлять вакансии вовсе
    candidate_client_vacancy = await Vacancy.create(
        employer=other, title="Чужая", status=VacancyStatus.PUBLISHED
    )
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    candidate_update = await _update(
        client, candidate_client_vacancy.id, title="Перехвачено"
    )
    assert candidate_update.status_code == 403
    assert candidate_update.json()["error"]["code"] == "wrong_role"


async def test_questions_cannot_be_replaced_after_applications(
    client: AsyncClient,
) -> None:
    """Раздел 83: исторические ответы отклика удалять нельзя.

    Отдельный тест: нужен отклик с уже сохранённым ответом — состояние
    тяжелее, чем у остальных проверок PATCH, и диагностика важнее компактности.
    """
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


# --- Список кабинета работодателя ---------------------------------------------


async def test_employer_vacancy_list(client: AsyncClient) -> None:
    # 1. Список содержит только свои вакансии, в порядке новизны
    other = await _other_employer()
    await Vacancy.create(employer=other, title="Чужая", status=VacancyStatus.PUBLISHED)
    await _employer(client)
    first = await _created_vacancy(client, title="Первая")
    second = await _created_vacancy(client, title="Вторая")
    own = (await client.get("/api/employer/vacancies")).json()
    assert own["total"] == 2
    assert [item["id"] for item in own["items"]] == [second["id"], first["id"]]
    assert all(item["applications_count"] == 0 for item in own["items"])

    # 2. Пагинация не пересекается и корректно считает total
    for index in range(3):
        await _created_vacancy(client, title=f"Вакансия {index}")
    page_one = (await client.get("/api/employer/vacancies?limit=2&offset=0")).json()
    page_two = (await client.get("/api/employer/vacancies?limit=2&offset=2")).json()
    assert page_one["total"] == 5
    assert len(page_one["items"]) == 2
    assert {item["id"] for item in page_one["items"]}.isdisjoint(
        {item["id"] for item in page_two["items"]}
    )

    # 3. Список кабинета работодателя недоступен кандидату
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    assert (await client.get("/api/employer/vacancies")).status_code == 403


# --- Связка с лентой и откликом ------------------------------------------------


async def test_vacancy_feed_and_apply_integration(client: AsyncClient) -> None:
    # 1. Вакансия работает в подборе теми условиями, что заданы при создании
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

    # 2. Закрытая вакансия откликов больше не принимает
    await _employer(client)
    closed_source = await _created_vacancy(client, status="published")
    assert (
        await _update(client, closed_source["id"], status="closed")
    ).status_code == 200

    await _candidate(client)
    closed_apply = await client.post(f"/api/vacancies/{closed_source['id']}/apply")
    assert closed_apply.status_code == 409
    assert closed_apply.json()["error"]["code"] == "vacancy_not_published"


# --- Удаление черновика ----------------------------------------------------------
#
# Баг с демо: кнопка удаления черновика в кабинете ничего не делает, потому что
# `DELETE /api/vacancies/{id}` в `app/vacancies/router.py` не заведён вовсе (там
# только POST/GET/PATCH). Ниже — контракт, под который тест написан заранее:
# работодатель может удалить свой черновик (`204`), но не опубликованную или
# закрытую вакансию (`409`) — по той же логике, что запрещает `published →
# draft` (раздел 57): по вакансии, которая хоть раз была опубликована, уже
# могли прийти отклики, и удалять её без разбора нельзя.


async def _delete(client: AsyncClient, vacancy_id: int):
    return await client.delete(f"/api/vacancies/{vacancy_id}")


async def test_vacancy_draft_deletion(client: AsyncClient) -> None:
    # 1. Без сессии — 401
    assert (await _delete(client, 1)).status_code == 401

    # 2. Кандидату эндпоинт недоступен вовсе
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    wrong_role = await _delete(client, 1)
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    # 3. Чужой черновик — 404, а не 403, и он не пропадает
    other = await _other_employer()
    foreign_draft = await Vacancy.create(
        employer=other, title="Чужой черновик", status=VacancyStatus.DRAFT
    )
    await _employer(client)
    foreign_delete = await _delete(client, foreign_draft.id)
    assert foreign_delete.status_code == 404
    assert foreign_delete.json()["error"]["code"] == "vacancy_not_found"
    assert await Vacancy.filter(id=foreign_draft.id).exists()

    # 4. Несуществующая вакансия — тоже 404
    assert (await _delete(client, 999999)).status_code == 404

    # 5. Свой черновик удаляется: `204`, и вакансия действительно исчезает
    own_draft = await _created_vacancy(client)
    deleted = await _delete(client, own_draft["id"])
    assert deleted.status_code == 204, deleted.text
    assert not await Vacancy.filter(id=own_draft["id"]).exists()
    assert (await client.get(f"/api/vacancies/{own_draft['id']}")).status_code == 404

    # 6. Опубликованную вакансию удалить нельзя — только закрыть
    published = await _created_vacancy(client, status="published")
    published_delete = await _delete(client, published["id"])
    assert published_delete.status_code == 409
    assert await Vacancy.filter(id=published["id"]).exists()

    # 7. Закрытую — тоже нельзя: с ней могла быть связана история откликов
    closed = await _created_vacancy(client, status="published")
    assert (await _update(client, closed["id"], status="closed")).status_code == 200
    closed_delete = await _delete(client, closed["id"])
    assert closed_delete.status_code == 409
    assert await Vacancy.filter(id=closed["id"]).exists()


# --- Публичная ссылка на вакансию ------------------------------------------------
#
# Баг с демо: `{APP_URL}/v/{public_token}` никуда не ведёт — на backend нет
# эндпоинта, который резолвил бы токен в вакансию (`GET /vacancies/{id}`
# принимает только числовой id), а на фронтенде нет роута `/v/:token`.
# Контракт для backend-части: `GET /vacancies/public/{token}` отдаёт тот же
# `VacancyRead`, что кандидат получает из `GET /vacancies/{id}` — без
# `public_token`/`public_url`/`applications_count` и без отсекающих условий
# в `validation_rules`.


async def _public(client: AsyncClient, token: str):
    return await client.get(f"/api/vacancies/public/{token}")


async def test_vacancy_public_link_by_token(client: AsyncClient) -> None:
    # 1. Без сессии ссылка недоступна — как и обычная карточка вакансии.
    # Проверка до логина: авторизация проверяется раньше, чем токен резолвится
    # в вакансию, поэтому реальный токен здесь не нужен.
    unauthenticated = await _public(client, "irrelevant-token")
    assert unauthenticated.status_code == 401

    await _employer(client)
    published = await _created_vacancy(
        client,
        status="published",
        questions=[
            {
                "question": "Есть ли медкнижка?",
                "type": "boolean",
                "required": True,
                "validation_rules": {"must_equal": True},
            }
        ],
    )
    token = published["public_token"]
    assert token

    # 2. Кандидат по ссылке видит вакансию в том же урезанном виде, что и по id
    await _candidate(client)
    by_token = (await _public(client, token)).json()
    by_id = (await client.get(f"/api/vacancies/{published['id']}")).json()
    assert by_token == by_id
    assert by_token["public_token"] is None
    assert by_token["public_url"] is None
    assert by_token["applications_count"] is None
    assert by_token["questions"][0]["validation_rules"] == {}

    # 3. Несуществующий токен — 404, не 422: как и с id, наружу не раскрывается,
    # существует вакансия или нет
    unknown_token = await _public(client, "does-not-exist")
    assert unknown_token.status_code == 404
    assert unknown_token.json()["error"]["code"] == "vacancy_not_found"

    # 4. Черновик по ссылке не откроется — у него вообще нет токена, но и сам
    # факт закрытия ссылки для чужой аудитории проверяем на закрытой вакансии
    await _employer(client)
    closed = await _created_vacancy(client, status="published")
    assert (await _update(client, closed["id"], status="closed")).status_code == 200
    closed_token = closed["public_token"]

    other_candidate_id = next(_candidate_ids)
    await _login(client, other_candidate_id, UserRole.CANDIDATE)
    closed_by_token = await _public(client, closed_token)
    assert closed_by_token.status_code == 404
    assert closed_by_token.json()["error"]["code"] == "vacancy_not_found"
