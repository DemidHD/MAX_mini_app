"""POST/GET /vacancies/:id/referral. Экран R01 UX-карты, функция 32, раздел 68
тех-доки.

UX-карта описывает R01 как «Общее»: рекомендовать вакансию может любая роль
(«Кнопка "Порекомендовать знакомого"» — кандидатский сценарий), не только
работодатель-владелец. Эти тесты фиксируют доступ для обеих ролей и то, что
список ссылок не раскрывает чужие коды.
"""

from itertools import count

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.enums import UserRole
from app.main import app
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(960000)
_candidate_ids = count(961000)

FULL_VACANCY = {
    "title": "Бариста в центре",
    "location": "Москва",
    "salary_min": "60000",
    "salary_max": "90000",
    "schedule": "full_time",
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    yield
    await Vacancy.filter(employer_id__gte=960000, employer_id__lt=961000).delete()


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _published_vacancy(client: AsyncClient) -> tuple[User, int]:
    employer = await _login(client, next(_employer_ids), UserRole.EMPLOYER)
    response = await client.post(
        "/api/vacancies", json={**FULL_VACANCY, "status": "published"}
    )
    assert response.status_code == 201, response.text
    return employer, response.json()["id"]


async def _draft_vacancy(client: AsyncClient) -> tuple[User, int]:
    employer = await _login(client, next(_employer_ids), UserRole.EMPLOYER)
    response = await client.post("/api/vacancies", json={"title": "Черновик"})
    assert response.status_code == 201, response.text
    return employer, response.json()["id"]


# --- Доступ ----------------------------------------------------------------


async def test_referral_requires_auth_and_role(client: AsyncClient) -> None:
    _, vacancy_id = await _published_vacancy(client)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as guest_client:
        guest = await guest_client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert guest.status_code == 401

    without_role_id = next(_candidate_ids)
    response = await client.post(
        "/api/auth/max",
        json={
            "init_data": build_init_data(
                user=max_user_payload(user_id=without_role_id)
            )
        },
    )
    assert response.status_code == 200, response.text
    no_role = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert no_role.status_code == 403
    assert no_role.json()["error"]["code"] == "role_not_selected"


async def test_candidate_can_create_and_list_own_referral_link(
    client: AsyncClient,
) -> None:
    """Главный сценарий: R01 для кандидата, а не только для работодателя."""
    _, vacancy_id = await _published_vacancy(client)

    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    created = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"]
    assert f"?ref={body['code']}" in body["url"]

    listed = await client.get(f"/api/vacancies/{vacancy_id}/referral")
    assert listed.status_code == 200, listed.text
    assert [item["code"] for item in listed.json()["items"]] == [body["code"]]


async def test_employer_owner_flow_still_works(client: AsyncClient) -> None:
    """Регрессия: у владельца вакансии сценарий не должен был измениться."""
    employer, vacancy_id = await _published_vacancy(client)

    created = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert created.status_code == 201, created.text

    listed = await client.get(f"/api/vacancies/{vacancy_id}/referral")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1


async def test_referral_list_does_not_leak_other_users_links(
    client: AsyncClient,
) -> None:
    """Приватность: список ссылок вакансии — только свои, а не все чужие коды."""
    employer, vacancy_id = await _published_vacancy(client)
    employer_created = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert employer_created.status_code == 201, employer_created.text
    employer_code = employer_created.json()["code"]

    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    candidate_created = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert candidate_created.status_code == 201, candidate_created.text
    candidate_code = candidate_created.json()["code"]
    assert candidate_code != employer_code

    candidate_list = await client.get(f"/api/vacancies/{vacancy_id}/referral")
    assert [item["code"] for item in candidate_list.json()["items"]] == [
        candidate_code
    ]


async def test_referral_on_own_draft_vacancy_requires_publishing_first(
    client: AsyncClient,
) -> None:
    _, vacancy_id = await _draft_vacancy(client)

    response = await client.post(f"/api/vacancies/{vacancy_id}/referral")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vacancy_not_published"


async def test_referral_on_someone_elses_draft_is_not_found(
    client: AsyncClient,
) -> None:
    """Черновик чужого работодателя не раскрывается — 404, не 409."""
    _, draft_id = await _draft_vacancy(client)

    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    response = await client.post(f"/api/vacancies/{draft_id}/referral")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"

    listed = await client.get(f"/api/vacancies/{draft_id}/referral")
    assert listed.status_code == 404


async def test_referral_on_missing_vacancy_is_not_found(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    response = await client.post("/api/vacancies/999999999/referral")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"
