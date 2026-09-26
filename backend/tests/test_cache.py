"""Redis-кэш: наполнение, инвалидация, устойчивость к недоступному Redis.

Остальной набор тестов держит кэш выключенным (`conftest._flush_cache`) —
их фикстуры меняют `Vacancy`/`User` напрямую через ORM в обход
`app.vacancies.service`/`app.auth.service`, а значит и мимо инвалидации.
Здесь кэш явно включён, а все изменения идут только через реальные
эндпоинты — ровно тем путём, которым пользуется продовый код.
"""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest_asyncio
from httpx import AsyncClient

from app.auth.models import Session
from app.candidates.models import CandidateProfile
from app.core import cache
from app.core.config import settings
from app.core.enums import UserRole
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(950000)
_candidate_ids = count(951000)

FULL_VACANCY = {
    "title": "Бариста в центре",
    "location": "Москва",
    "salary_min": "60000",
    "salary_max": "90000",
    "schedule": "full_time",
}


@pytest_asyncio.fixture(autouse=True)
async def _enable_cache():
    """Единственное место, где кэш должен быть включён. Выполняется после
    `conftest._flush_cache` (тот выключает) и переопределяет это значение
    для тестов этого файла."""
    cache.set_enabled(True)
    yield
    cache.set_enabled(False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    yield
    await Vacancy.filter(employer_id__gte=950000, employer_id__lt=951000).delete()


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


async def _candidate(client: AsyncClient) -> User:
    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await CandidateProfile.create(
        user_id=candidate.user_id,
        desired_role="Бариста",
        city="Москва",
        salary=Decimal("70000"),
        schedule="full_time",
        experience_months=24,
        available_from=date(2026, 10, 1),
    )
    return candidate


async def _publish(client: AsyncClient, **overrides) -> dict:
    payload = {**FULL_VACANCY, **overrides, "status": "published"}
    response = await client.post("/api/vacancies", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- Примитивы кэша (app.core.cache) ----------------------------------------


async def test_get_set_delete_roundtrip() -> None:
    key = "cache:test:roundtrip"
    assert await cache.get_json(key) is None

    await cache.set_json(key, {"a": 1}, ttl_seconds=30)
    assert await cache.get_json(key) == {"a": 1}

    await cache.delete(key)
    assert await cache.get_json(key) is None


async def test_delete_prefix_removes_only_matching_keys() -> None:
    await cache.set_json("cache:test:prefix:1", "a", ttl_seconds=30)
    await cache.set_json("cache:test:prefix:2", "b", ttl_seconds=30)
    await cache.set_json("cache:test:other", "c", ttl_seconds=30)

    await cache.delete_prefix("cache:test:prefix:")

    assert await cache.get_json("cache:test:prefix:1") is None
    assert await cache.get_json("cache:test:prefix:2") is None
    assert await cache.get_json("cache:test:other") == "c"


async def test_cache_degrades_silently_when_redis_unreachable(
    client: AsyncClient,
) -> None:
    """Требование задачи №6: недоступный Redis — промах, а не сбой запроса."""
    original_url = settings.redis_url
    settings.redis_url = "redis://localhost:9"  # порт, на котором никто не слушает
    try:
        await cache.connect()
        assert await cache.get_json("cache:test:anything") is None
        await cache.set_json("cache:test:anything", "value", ttl_seconds=30)
        await cache.delete("cache:test:anything")
        await cache.delete_prefix("cache:test:")

        # И сквозь настоящий запрос: без кэша эндпоинт всё равно отвечает 200
        await _employer(client)
        response = await client.get("/api/employer/vacancies")
        assert response.status_code == 200, response.text
    finally:
        await cache.disconnect()
        settings.redis_url = original_url
        await cache.connect()


# --- Пул подбора ленты (app.matching.service) -------------------------------


async def test_feed_pool_is_cached_and_invalidated_on_new_vacancy(
    client: AsyncClient,
) -> None:
    await _employer(client)
    await _publish(client, title="Первая вакансия")

    await _candidate(client)
    first = await client.get("/api/vacancies/feed")
    assert first.status_code == 200, first.text
    assert [item["title"] for item in first.json()["items"]] == ["Первая вакансия"]

    cached_pool = await cache.get_json("cache:feed:pool")
    assert cached_pool is not None
    assert len(cached_pool) == 1

    await _employer(client)
    await _publish(client, title="Вторая вакансия")

    # Публикация инвалидирует пул целиком
    assert await cache.get_json("cache:feed:pool") is None

    await _candidate(client)
    second = await client.get("/api/vacancies/feed")
    titles = {item["title"] for item in second.json()["items"]}
    assert titles == {"Первая вакансия", "Вторая вакансия"}


# --- Список вакансий кабинета работодателя (app.vacancies.service) ---------


async def test_employer_vacancies_are_cached_and_invalidated_on_update(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    created = await _publish(client, title="Исходное название")
    vacancy_id = created["id"]

    first = await client.get("/api/employer/vacancies")
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["title"] == "Исходное название"

    cache_key = f"cache:employer_vacancies:{employer.user_id}:20:0"
    assert await cache.get_json(cache_key) is not None

    updated = await client.patch(
        f"/api/vacancies/{vacancy_id}", json={"title": "Новое название"}
    )
    assert updated.status_code == 200, updated.text

    # Правка инвалидирует все страницы этого работодателя
    assert await cache.get_json(cache_key) is None

    second = await client.get("/api/employer/vacancies")
    assert second.json()["items"][0]["title"] == "Новое название"


# --- Кандидатский вид вакансии (app.vacancies.service) ----------------------


async def test_candidate_vacancy_view_is_cached_and_invalidated_on_update(
    client: AsyncClient,
) -> None:
    employer = await _employer(client)
    created = await _publish(client, title="Исходное название")
    vacancy_id = created["id"]

    await _candidate(client)
    first = await client.get(f"/api/vacancies/{vacancy_id}")
    assert first.status_code == 200, first.text
    assert first.json()["title"] == "Исходное название"

    cache_key = f"cache:vacancy_view:{vacancy_id}"
    assert await cache.get_json(cache_key) is not None

    await _login(client, employer.user_id, UserRole.EMPLOYER)
    updated = await client.patch(
        f"/api/vacancies/{vacancy_id}", json={"title": "Новое название"}
    )
    assert updated.status_code == 200, updated.text
    assert await cache.get_json(cache_key) is None

    await _candidate(client)
    second = await client.get(f"/api/vacancies/{vacancy_id}")
    assert second.json()["title"] == "Новое название"


# --- Сессия (app.auth.service) ----------------------------------------------


async def test_session_lookup_is_cached_and_skips_last_used_write(
    client: AsyncClient,
) -> None:
    await _employer(client)
    session_id = client.cookies.get(settings.session_cookie_name)
    assert session_id

    first = await client.get("/api/users/me")
    assert first.status_code == 200, first.text
    session = await Session.get(id=session_id)
    first_last_used = session.last_used_at

    cached = await cache.get_json(f"cache:session:{session_id}")
    assert cached == {"user_id": first.json()["user_id"]}

    # Второй запрос обслуживается кэшем: запись `last_used_at` не повторяется
    second = await client.get("/api/users/me")
    assert second.status_code == 200, second.text
    session_after = await Session.get(id=session_id)
    assert session_after.last_used_at == first_last_used
