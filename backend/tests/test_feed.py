"""GET /api/vacancies/feed. Раздел 30 тех-доки.

Гвард-проверки и вся фильтрация по критериям собраны в сквозные сценарии.
После первого шага (который требует чистой базы для точного списка) все
остальные шаги фильтрации используют проверки "включено/не включено" по
конкретному заголовку вакансии — это устойчиво к накоплению вакансий из
предыдущих шагов того же теста. Инварианты пагинации на синтетически
одинаковых `created_at` оставлены отдельным тестом — там важна изоляция.
"""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from tortoise import Tortoise

from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import ApplicationStatus, CriterionType, UserRole, VacancyStatus
from app.matching import service as matching_service
from app.users.models import User
from app.vacancies.models import Vacancy, VacancyCriterion
from tests.factories import build_init_data, max_user_payload

EMPLOYER_ID = 740000


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Лента показывает все опубликованные вакансии, поэтому база общая
    между тестами мешает: чистим перед каждым."""
    await Vacancy.all().delete()
    yield


async def _employer() -> User:
    employer = await User.get_or_none(user_id=EMPLOYER_ID)
    if employer is None:
        employer = await User.create(
            user_id=EMPLOYER_ID, first_name="Работодатель", role=UserRole.EMPLOYER
        )
    return employer


async def _vacancy(
    title: str,
    *,
    status: VacancyStatus = VacancyStatus.PUBLISHED,
    criteria: list[tuple[CriterionType, dict, bool]] | None = None,
    salary_max: Decimal | None = Decimal("90000"),
) -> Vacancy:
    vacancy = await Vacancy.create(
        employer=await _employer(),
        title=title,
        location="Москва",
        salary_max=salary_max,
        schedule="full_time",
        status=status,
    )
    for criterion_type, value, required in criteria or []:
        await VacancyCriterion.create(
            vacancy=vacancy, type=criterion_type, required=required, value=value
        )
    return vacancy


async def _login_candidate(
    client: AsyncClient, user_id: int, *, with_profile: bool = True, **profile_kwargs
) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200
    await User.filter(user_id=user_id).update(role=UserRole.CANDIDATE)

    if with_profile:
        defaults = {
            "desired_role": "Бариста",
            "city": "Москва",
            "salary": Decimal("70000"),
            "schedule": "full_time",
            "experience_months": 24,
            "available_from": date(2026, 10, 1),
        }
        await CandidateProfile.create(user_id=user_id, **(defaults | profile_kwargs))
    return await User.get(user_id=user_id)


async def _feed(client: AsyncClient, **params) -> dict:
    response = await client.get("/api/vacancies/feed", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _titles(body: dict) -> list[str]:
    return [item["title"] for item in body["items"]]


# --- Доступ -------------------------------------------------------------------


async def test_feed_access_guards(client: AsyncClient) -> None:
    # 1. Без выбранной роли и с чужой ролью лента недоступна
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=741001))},
    )
    without_role = await client.get("/api/vacancies/feed")
    assert without_role.status_code == 403
    assert without_role.json()["error"]["code"] == "role_not_selected"

    await User.filter(user_id=741001).update(role=UserRole.EMPLOYER)
    as_employer = await client.get("/api/vacancies/feed")
    assert as_employer.status_code == 403
    assert as_employer.json()["error"]["code"] == "wrong_role"

    # 2. Без сессии — 401
    client.cookies.clear()
    assert (await client.get("/api/vacancies/feed")).status_code == 401


# --- Фильтрация по критериям и содержимое карточки -----------------------------


async def test_feed_criteria_filtering(client: AsyncClient) -> None:
    # 1. Показываются только опубликованные вакансии — база здесь ещё чистая,
    # поэтому список можно сверить точно
    await _login_candidate(client, 741002)
    await _vacancy("Опубликованная")
    await _vacancy("Черновик", status=VacancyStatus.DRAFT)
    await _vacancy("Закрытая", status=VacancyStatus.CLOSED)
    assert _titles(await _feed(client)) == ["Опубликованная"]

    # 2. Вакансия без условий видна всем
    await _login_candidate(client, 741003)
    await _vacancy("Без условий")
    assert "Без условий" in _titles(await _feed(client))

    # 3. Обязательное условие прячет несовпадающую вакансию и показывает подходящую
    await _login_candidate(client, 741004, city="Москва")
    await _vacancy(
        "Казань обязательна", criteria=[(CriterionType.LOCATION, {"city": "Казань"}, True)]
    )
    await _vacancy(
        "Москва подходит 741004",
        criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)],
    )
    required_titles = _titles(await _feed(client))
    assert "Москва подходит 741004" in required_titles
    assert "Казань обязательна" not in required_titles

    # 4. Необязательное условие вакансию не прячет, даже если оно не подходит
    await _login_candidate(client, 741005, city="Москва")
    await _vacancy(
        "Желательно Казань", criteria=[(CriterionType.LOCATION, {"city": "Казань"}, False)]
    )
    assert "Желательно Казань" in _titles(await _feed(client))

    # 5. Нет данных в профиле — не повод прятать вакансию
    await _login_candidate(client, 741006, city=None)
    await _vacancy(
        "Нужна Москва 741006",
        criteria=[(CriterionType.LOCATION, {"city": "Москва"}, True)],
    )
    assert "Нужна Москва 741006" in _titles(await _feed(client))

    # 6. Ожидания по зарплате выше потолка вакансии — вакансия скрыта
    await _login_candidate(client, 741007, salary=Decimal("120000"))
    await _vacancy(
        "Потолок ниже ожиданий", criteria=[(CriterionType.SALARY, {"max": 80000}, True)]
    )
    assert "Потолок ниже ожиданий" not in _titles(await _feed(client))

    # 7. Некорректный предел зарплаты не должен ронять ленту целиком
    await _login_candidate(client, 741014)
    await _vacancy(
        "Некорректный предел",
        criteria=[(CriterionType.SALARY, {"max": "NaN"}, True)],
        salary_max=None,
    )
    assert "Некорректный предел" in _titles(await _feed(client))

    # 8. Опыт и дата выхода применяются вместе
    await _login_candidate(
        client, 741008, experience_months=6, available_from=date(2026, 12, 1)
    )
    await _vacancy(
        "Нужен опыт от 2 лет", criteria=[(CriterionType.EXPERIENCE, {"min_months": 24}, True)]
    )
    await _vacancy(
        "Выход до октября",
        criteria=[(CriterionType.AVAILABLE_FROM, {"date": "2026-10-01"}, True)],
    )
    await _vacancy(
        "Опыта хватает 741008",
        criteria=[(CriterionType.EXPERIENCE, {"min_months": 3}, True)],
    )
    experience_titles = _titles(await _feed(client))
    assert "Опыта хватает 741008" in experience_titles
    assert "Нужен опыт от 2 лет" not in experience_titles
    assert "Выход до октября" not in experience_titles

    # 9. Отклик на вакансию убирает её из ленты
    applying_candidate = await _login_candidate(client, 741009)
    applied = await _vacancy("Уже откликнулся")
    await _vacancy("Новая 741009")
    await Application.create(
        vacancy=applied, candidate=applying_candidate, status=ApplicationStatus.SCREENING
    )
    applied_titles = _titles(await _feed(client))
    assert "Новая 741009" in applied_titles
    assert "Уже откликнулся" not in applied_titles

    # 10. Без профиля лента пуста
    await _login_candidate(client, 741010, with_profile=False)
    await _vacancy("Есть вакансия")
    empty_body = await _feed(client)
    assert empty_body["items"] == []
    assert empty_body["total"] == 0

    # 11. Неизвестный тип критерия (например, от более новой версии кода)
    # не должен ронять чтение всей ленты — подбор просто не берёт его в расчёт
    await _login_candidate(client, 741020)
    broken = await _vacancy("С неизвестным условием")
    await Tortoise.get_connection("default").execute_query(
        "INSERT INTO vacancy_criteria (vacancy_id, type, required, value, created_at)"
        " VALUES ($1, 'education', TRUE, '{\"level\": \"higher\"}'::jsonb, NOW())",
        [broken.id],
    )
    await _vacancy("Обычная 741020")
    unknown_criterion_titles = _titles(await _feed(client))
    assert "С неизвестным условием" in unknown_criterion_titles
    assert "Обычная 741020" in unknown_criterion_titles

    # 12. Карточка ленты содержит условия вакансии и её зарплатный потолок
    await _login_candidate(client, 741011)
    await _vacancy(
        "С условиями", criteria=[(CriterionType.SCHEDULE, {"schedule": "full_time"}, True)]
    )
    card = next(
        item for item in (await _feed(client))["items"] if item["title"] == "С условиями"
    )
    assert card["location"] == "Москва"
    assert card["salary_max"] == "90000.00"
    assert card["criteria"] == [
        {"type": "schedule", "required": True, "value": {"schedule": "full_time"}}
    ]


# --- Пагинация ------------------------------------------------------------------


async def test_feed_pagination(client: AsyncClient) -> None:
    # 1. Обычная пагинация: страницы не пересекаются, total не меньше выборки
    await _login_candidate(client, 741012)
    for index in range(3):
        await _vacancy(f"Вакансия {index}")
    first = await _feed(client, limit=2)
    second = await _feed(client, limit=2, offset=2)
    assert len(first["items"]) == 2
    assert first["total"] >= 3
    assert len(second["items"]) >= 1
    assert set(_titles(first)).isdisjoint(_titles(second))

    # 2. total — это полное число подходящих вакансий, а не размер страницы
    # (изолируем от вакансий шага 1, чтобы сравнить с точным числом)
    await Vacancy.all().delete()
    await _login_candidate(client, 741022)
    for index in range(3):
        await _vacancy(f"Отдельная вакансия {index}")
    counted = await _feed(client, limit=2)
    assert len(counted["items"]) == 2
    assert counted["total"] == 3
    assert len(_titles(await _feed(client, limit=2, offset=2))) == 1

    # 3. Некорректная пагинация отклоняется
    await _login_candidate(client, 741013)
    invalid = await client.get("/api/vacancies/feed", params={"limit": 500})
    assert invalid.status_code == 422

    # 4. Внутренний размер батча сканирования не должен терять подходящие
    # вакансии за неподходящими более новыми — тоже изолируем от шагов выше
    await Vacancy.all().delete()
    await _login_candidate(client, 741015, city="Москва")
    await _vacancy("Старая подходящая")
    for index in range(3):
        await _vacancy(
            f"Новая неподходящая {index}",
            criteria=[(CriterionType.LOCATION, {"city": "Казань"}, True)],
        )
    original_batch_size = matching_service.FEED_SCAN_BATCH_SIZE
    matching_service.FEED_SCAN_BATCH_SIZE = 2
    try:
        body = await _feed(client)
    finally:
        matching_service.FEED_SCAN_BATCH_SIZE = original_batch_size
    assert _titles(body) == ["Старая подходящая"]
    assert body["total"] == 1


async def test_pages_do_not_overlap_for_equal_created_at(client: AsyncClient) -> None:
    """Одинаковое время создания не должно перемешивать страницы."""
    await _login_candidate(client, 741021)
    employer = await _employer()
    connection = Tortoise.get_connection("default")
    for index in range(4):
        await connection.execute_query(
            "INSERT INTO vacancies (employer_id, title, status, created_at, updated_at)"
            " VALUES ($1, $2, 'published', TIMESTAMPTZ '2026-09-01 10:00:00+00',"
            " TIMESTAMPTZ '2026-09-01 10:00:00+00')",
            [employer.user_id, f"Одновременная {index}"],
        )

    first = _titles(await _feed(client, limit=2))
    second = _titles(await _feed(client, limit=2, offset=2))

    assert len(set(first + second)) == 4
