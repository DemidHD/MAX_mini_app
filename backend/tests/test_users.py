"""Профиль, роль и ограничения доступа. Разделы 8, 9, 11, 12, 27.

Весь путь — от первого чтения профиля до смены роли — собран в один
сквозной сценарий с пронумерованными шагами, включая проверки на
невалидный ввод по пути.
"""

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


async def test_user_profile_and_role_flow(client: AsyncClient) -> None:
    # 1. Без сессии профиль недоступен
    unauthenticated = await client.get("/api/users/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthorized"

    # 2. После логина видно профиль без роли и без аватарки
    await _login(client, 710001)
    me = await client.get("/api/users/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user_id"] == 710001
    assert body["role"] is None
    assert body["has_avatar"] is False

    # 3. Имя и фамилию можно изменить
    renamed = await client.patch(
        "/api/users/me/profile",
        json={"first_name": "Алексей", "last_name": "Иванов"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["first_name"] == "Алексей"
    assert (await User.get(user_id=710001)).last_name == "Иванов"

    # 4. Пустое и null имя отклоняются, сохранённое значение не меняется
    blank_name = await client.patch(
        "/api/users/me/profile", json={"first_name": "  "}
    )
    assert blank_name.status_code == 422
    assert blank_name.json()["error"]["code"] == "validation_error"

    null_name = await client.patch("/api/users/me/profile", json={"first_name": None})
    assert null_name.status_code == 422
    assert null_name.json()["error"]["code"] == "validation_error"
    assert (await User.get(user_id=710001)).first_name == "Алексей"

    # 5. user_id в теле запроса не позволяет менять чужой профиль
    victim = await User.create(user_id=710004, first_name="Жертва")
    await client.patch(
        "/api/users/me/profile",
        json={"user_id": victim.user_id, "first_name": "Взломщик"},
    )
    assert (await User.get(user_id=710004)).first_name == "Жертва"
    assert (await User.get(user_id=710001)).first_name == "Взломщик"

    # 6. Роль выбирается и логируется аналитикой
    selected = await client.patch("/api/users/me/role", json={"role": "employer"})
    assert selected.status_code == 200
    assert selected.json()["role"] == "employer"
    assert (await User.get(user_id=710001)).role == UserRole.EMPLOYER
    assert await AnalyticsEvent.filter(
        user_id=710001, event_name="role_selected"
    ).exists()

    # 7. Неизвестная роль отклоняется
    unknown_role = await client.patch("/api/users/me/role", json={"role": "admin"})
    assert unknown_role.status_code == 422

    # 8. Тех-дока не запрещает смену роли — она разрешена и тоже логируется
    changed = await client.patch("/api/users/me/role", json={"role": "candidate"})
    assert changed.status_code == 200
    assert (await User.get(user_id=710001)).role == UserRole.CANDIDATE
    event = (
        await AnalyticsEvent.filter(user_id=710001, event_name="role_selected")
        .order_by("-timestamp")
        .first()
    )
    assert event.payload == {"role": "candidate", "previous_role": "employer"}

    # 9. Повторный выбор той же роли — идемпотентен
    repeated = await client.patch("/api/users/me/role", json={"role": "candidate"})
    assert repeated.status_code == 200
    assert repeated.json()["role"] == "candidate"
