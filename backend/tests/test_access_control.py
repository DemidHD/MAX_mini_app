"""Сводная проверка прав доступа. Разделы 10, 11, 12, 57 тех-доки.

Отдельные проверки есть в каждом модуле; здесь — общая сетка, которая ловит
новый эндпоинт, выпущенный без защиты: личность пользователя определяется
только серверной сессией, а роль решает, что ему доступно.
"""

from itertools import count

import pytest
from httpx import AsyncClient

from app.core.enums import UserRole
from app.main import app
from app.users.models import User
from tests.factories import build_init_data, max_user_payload

_user_ids = count(840000)

# Эндпоинты, которым сессия не нужна по определению
PUBLIC_PATHS = frozenset({"/api/auth/max", "/health"})

# Эндпоинты P0 и роли, которым они доступны (раздел 27).
# `None` означает «любая авторизованная роль, в том числе не выбранная».
ROLE_MATRIX: tuple[tuple[str, str, UserRole | None], ...] = (
    ("GET", "/api/users/me", None),
    ("PATCH", "/api/users/me/profile", None),
    ("PATCH", "/api/users/me/role", None),
    ("GET", "/api/candidate/profile", UserRole.CANDIDATE),
    ("PATCH", "/api/candidate/profile", UserRole.CANDIDATE),
    ("GET", "/api/vacancies/feed", UserRole.CANDIDATE),
    ("POST", "/api/vacancies", UserRole.EMPLOYER),
    ("PATCH", "/api/vacancies/1", UserRole.EMPLOYER),
    ("GET", "/api/employer/vacancies", UserRole.EMPLOYER),
    ("GET", "/api/employer/vacancies/1/candidates", UserRole.EMPLOYER),
    ("POST", "/api/vacancies/1/apply", UserRole.CANDIDATE),
    ("GET", "/api/applications/1/screening", UserRole.CANDIDATE),
    ("POST", "/api/applications/1/screening", UserRole.CANDIDATE),
    ("POST", "/api/applications/1/decision", UserRole.EMPLOYER),
    ("POST", "/api/vacancies/1/slots", UserRole.EMPLOYER),
    ("DELETE", "/api/vacancies/1/slots/1", UserRole.EMPLOYER),
    ("POST", "/api/matches/1/book", UserRole.CANDIDATE),
)


def _api_endpoints() -> list[tuple[str, str]]:
    """Все эндпоинты приложения по его же OpenAPI-схеме."""
    endpoints: list[tuple[str, str]] = []
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            endpoints.append((method.upper(), path))
    return endpoints


def _fill(path: str) -> str:
    """Подставляет в путь любые идентификаторы: до данных дело не дойдёт."""
    result = path
    while "{" in result:
        start = result.index("{")
        end = result.index("}", start)
        result = result[:start] + "1" + result[end + 1 :]
    return result


async def _login(client: AsyncClient, role: UserRole | None) -> User:
    user_id = next(_user_ids)
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    if role is not None:
        await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _call(client: AsyncClient, method: str, path: str):
    return await client.request(method, path, json={})


@pytest.mark.parametrize(
    ("method", "path"),
    [
        (method, path)
        for method, path in _api_endpoints()
        if path not in PUBLIC_PATHS and path.startswith("/api")
    ],
)
async def test_every_api_endpoint_requires_session(
    client: AsyncClient, method: str, path: str
) -> None:
    """Раздел 10: защищённые эндпоинты получают пользователя только из сессии."""
    response = await _call(client, method, _fill(path))

    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path", "role"), ROLE_MATRIX)
async def test_endpoint_is_closed_for_user_without_role(
    client: AsyncClient, method: str, path: str, role: UserRole | None
) -> None:
    """Раздел 12: до выбора роли доступны только onboarding-эндпоинты."""
    await _login(client, None)

    response = await _call(client, method, path)

    if role is None:
        assert response.status_code != 403
        return
    assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
    assert response.json()["error"]["code"] == "role_not_selected"


@pytest.mark.parametrize(
    ("method", "path", "role"),
    [(method, path, role) for method, path, role in ROLE_MATRIX if role is not None],
)
async def test_endpoint_is_closed_for_wrong_role(
    client: AsyncClient, method: str, path: str, role: UserRole
) -> None:
    """Кандидатские эндпоинты закрыты работодателю и наоборот."""
    other_role = (
        UserRole.EMPLOYER if role is UserRole.CANDIDATE else UserRole.CANDIDATE
    )
    await _login(client, other_role)

    response = await _call(client, method, path)

    # Слоты вакансии читают обе стороны: это один эндпоинт на две роли
    assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
    assert response.json()["error"]["code"] == "wrong_role"


async def test_webhook_is_not_part_of_mini_app_api(client: AsyncClient) -> None:
    """Раздел 75: webhook не проходит обычную авторизацию Mini App."""
    paths = app.openapi()["paths"]

    assert not [path for path in paths if path.startswith("/api") and "webhook" in path]
