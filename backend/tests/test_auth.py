"""POST /api/auth/max: создание пользователя, сессия, current_step. Разделы 7, 10."""

import asyncio
from datetime import timedelta

from httpx import AsyncClient

from app.applications.models import Application
from app.auth import router as auth_router_module
from app.auth.models import Session
from app.auth.service import cleanup_expired_sessions
from app.candidates.models import CandidateProfile
from app.core.config import settings
from app.core.database import utcnow
from app.core.enums import ApplicationStatus, UserRole
from app.core.rate_limit import SlidingWindowRateLimiter
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload


async def _auth(client: AsyncClient, user_id: int, **user_kwargs) -> dict:
    payload = max_user_payload(user_id=user_id, **user_kwargs)
    response = await client.post(
        "/api/auth/max", json={"init_data": build_init_data(user=payload)}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_first_login_creates_user_without_role(client: AsyncClient) -> None:
    body = await _auth(client, 700001)

    assert body["user"]["user_id"] == 700001
    # Авторизация роль не назначает (раздел 8)
    assert body["user"]["role"] is None
    assert body["current_step"] == "role_selection"

    stored = await User.get(user_id=700001)
    assert stored.role is None


async def test_concurrent_first_logins_create_one_user(client: AsyncClient) -> None:
    """Параллельные первые входы не конфликтуют по users_pkey."""
    user_id = 700013
    init_data = build_init_data(user=max_user_payload(user_id=user_id))

    responses = await asyncio.gather(
        *(
            client.post("/api/auth/max", json={"init_data": init_data})
            for _ in range(8)
        )
    )

    assert [response.status_code for response in responses] == [200] * len(responses)
    assert await User.filter(user_id=user_id).count() == 1
    assert all(
        response.cookies.get(settings.session_cookie_name) is not None
        for response in responses
    )


async def test_login_sets_httponly_session_cookie(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=700002))},
    )

    cookie = response.cookies.get(settings.session_cookie_name)
    assert cookie is not None
    assert "httponly" in response.headers["set-cookie"].lower()

    session = await Session.get(id=cookie)
    assert session.user_id == 700002
    assert session.expires_at > utcnow()


async def test_invalid_init_data_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/max", json={"init_data": build_init_data(corrupt_hash=True)}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_init_data"
    assert await User.filter(user_id=100500).exists() is False


async def test_auth_rate_limit_returns_429(client: AsyncClient) -> None:
    original_limiter = auth_router_module.auth_rate_limiter
    auth_router_module.auth_rate_limiter = SlidingWindowRateLimiter(
        limit=2, window_seconds=60
    )
    try:
        responses = [
            await client.post(
                "/api/auth/max", json={"init_data": build_init_data(corrupt_hash=True)}
            )
            for _ in range(3)
        ]
    finally:
        auth_router_module.auth_rate_limiter = original_limiter

    assert [response.status_code for response in responses] == [401, 401, 429]
    assert responses[-1].json()["error"]["code"] == "rate_limited"
    assert int(responses[-1].headers["retry-after"]) >= 1


async def test_relogin_keeps_manually_changed_name(client: AsyncClient) -> None:
    await _auth(client, 700003, first_name="Иван", last_name="Петров")

    user = await User.get(user_id=700003)
    user.first_name = "Алексей"
    user.last_name = "Иванов"
    await user.save()

    # MAX снова присылает старые имя и фамилию
    body = await _auth(client, 700003, first_name="Иван", last_name="Петров")

    assert body["user"]["first_name"] == "Алексей"
    assert body["user"]["last_name"] == "Иванов"


async def test_relogin_refreshes_username_and_language(client: AsyncClient) -> None:
    await _auth(client, 700004, username="old_name", language_code="ru")
    before = await User.get(user_id=700004)

    await _auth(client, 700004, username="new_name", language_code="en")

    after = await User.get(user_id=700004)
    assert after.username == "new_name"
    assert after.language_code == "en"
    assert after.last_auth_at >= before.last_auth_at


async def test_current_step_for_candidate_without_profile(client: AsyncClient) -> None:
    await _auth(client, 700005)
    await User.filter(user_id=700005).update(role=UserRole.CANDIDATE)

    body = await _auth(client, 700005)

    assert body["current_step"] == "candidate_profile"


async def test_current_step_for_candidate_with_profile(client: AsyncClient) -> None:
    await _auth(client, 700006)
    await User.filter(user_id=700006).update(role=UserRole.CANDIDATE)
    await CandidateProfile.create(user_id=700006, desired_role="Бариста")

    body = await _auth(client, 700006)

    assert body["current_step"] == "feed"
    assert body["application_id"] is None


async def test_current_step_returns_active_application(client: AsyncClient) -> None:
    await _auth(client, 700007)
    await User.filter(user_id=700007).update(role=UserRole.CANDIDATE)
    await CandidateProfile.create(user_id=700007, desired_role="Официант")

    employer = await User.create(user_id=700008, first_name="Работодатель")
    vacancy = await Vacancy.create(employer=employer, title="Официант")
    application = await Application.create(
        vacancy=vacancy, candidate_id=700007, status=ApplicationStatus.SCREENING
    )

    body = await _auth(client, 700007)

    assert body["current_step"] == "application_status"
    assert body["application_id"] == application.id


async def test_current_step_ignores_finished_application(client: AsyncClient) -> None:
    await _auth(client, 700009)
    await User.filter(user_id=700009).update(role=UserRole.CANDIDATE)
    await CandidateProfile.create(user_id=700009, desired_role="Повар")

    employer = await User.create(user_id=700010, first_name="Работодатель")
    vacancy = await Vacancy.create(employer=employer, title="Повар")
    await Application.create(
        vacancy=vacancy, candidate_id=700009, status=ApplicationStatus.REJECTED
    )

    body = await _auth(client, 700009)

    assert body["current_step"] == "feed"


async def test_current_step_for_employer(client: AsyncClient) -> None:
    await _auth(client, 700011)
    await User.filter(user_id=700011).update(role=UserRole.EMPLOYER)

    body = await _auth(client, 700011)
    assert body["current_step"] == "vacancy_create"

    employer = await User.get(user_id=700011)
    await Vacancy.create(employer=employer, title="Администратор")

    body = await _auth(client, 700011)
    assert body["current_step"] == "employer_home"


async def test_expired_session_is_not_accepted(client: AsyncClient) -> None:
    body = await _auth(client, 700012)
    assert body["user"]["user_id"] == 700012

    session = await Session.filter(user_id=700012).first()
    session.expires_at = utcnow() - timedelta(minutes=1)
    await session.save()

    response = await client.get("/api/users/me")

    assert response.status_code == 401
    # Просроченная сессия удаляется
    assert await Session.filter(id=session.id).exists() is False


async def test_periodic_cleanup_removes_only_expired_sessions() -> None:
    user = await User.create(user_id=700014, first_name="Очистка")
    expired = await Session.create(
        user=user, expires_at=utcnow() - timedelta(minutes=1)
    )
    active = await Session.create(
        user=user, expires_at=utcnow() + timedelta(minutes=1)
    )

    deleted = await cleanup_expired_sessions(force=True)

    assert deleted >= 1
    assert await Session.filter(id=expired.id).exists() is False
    assert await Session.filter(id=active.id).exists() is True
