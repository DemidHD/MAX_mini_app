"""Профиль, роль и ограничения доступа. Разделы 8, 9, 11, 12, 27."""

from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
from app.core.enums import UserRole
from app.users.models import User
from tests.factories import build_init_data, max_user_payload


async def _login(client: AsyncClient, user_id: int) -> None:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200


async def test_me_requires_session(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_returns_profile(client: AsyncClient) -> None:
    await _login(client, 710001)

    response = await client.get("/api/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 710001
    assert body["role"] is None
    assert body["has_avatar"] is False


async def test_profile_name_can_be_changed(client: AsyncClient) -> None:
    await _login(client, 710002)

    response = await client.patch(
        "/api/users/me/profile",
        json={"first_name": "Алексей", "last_name": "Иванов"},
    )

    assert response.status_code == 200
    assert response.json()["first_name"] == "Алексей"
    stored = await User.get(user_id=710002)
    assert stored.last_name == "Иванов"


async def test_empty_first_name_is_rejected(client: AsyncClient) -> None:
    await _login(client, 710003)

    response = await client.patch("/api/users/me/profile", json={"first_name": "  "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_null_first_name_is_rejected(client: AsyncClient) -> None:
    await _login(client, 710010)

    response = await client.patch(
        "/api/users/me/profile", json={"first_name": None}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert (await User.get(user_id=710010)).first_name == "Иван"


async def test_user_id_in_body_does_not_change_another_user(client: AsyncClient) -> None:
    victim = await User.create(user_id=710004, first_name="Жертва")
    await _login(client, 710005)

    await client.patch(
        "/api/users/me/profile",
        json={"user_id": victim.user_id, "first_name": "Взломщик"},
    )

    assert (await User.get(user_id=710004)).first_name == "Жертва"
    assert (await User.get(user_id=710005)).first_name == "Взломщик"


async def test_role_is_selected_and_logged(client: AsyncClient) -> None:
    await _login(client, 710006)

    response = await client.patch("/api/users/me/role", json={"role": "employer"})

    assert response.status_code == 200
    assert response.json()["role"] == "employer"
    assert (await User.get(user_id=710006)).role == UserRole.EMPLOYER
    assert await AnalyticsEvent.filter(
        user_id=710006, event_name="role_selected"
    ).exists()


async def test_unknown_role_is_rejected(client: AsyncClient) -> None:
    await _login(client, 710007)

    response = await client.patch("/api/users/me/role", json={"role": "admin"})

    assert response.status_code == 422


async def test_role_can_be_changed(client: AsyncClient) -> None:
    """Тех-дока не запрещает смену роли, поэтому она разрешена и логируется."""
    await _login(client, 710008)
    await client.patch("/api/users/me/role", json={"role": "candidate"})

    response = await client.patch("/api/users/me/role", json={"role": "employer"})

    assert response.status_code == 200
    assert (await User.get(user_id=710008)).role == UserRole.EMPLOYER
    event = (
        await AnalyticsEvent.filter(user_id=710008, event_name="role_selected")
        .order_by("-timestamp")
        .first()
    )
    assert event.payload == {"role": "employer", "previous_role": "candidate"}


async def test_repeated_same_role_is_idempotent(client: AsyncClient) -> None:
    await _login(client, 710009)
    await client.patch("/api/users/me/role", json={"role": "candidate"})

    response = await client.patch("/api/users/me/role", json={"role": "candidate"})

    assert response.status_code == 200
    assert response.json()["role"] == "candidate"
