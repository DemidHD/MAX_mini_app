"""Навыки кандидата: справочник, `skill_ids` в профиле, подсказка из резюме,
отображение работодателю. Не из тех-доки — продуктовое решение.

`GET /api/skills`, `PATCH /candidate/profile` (поле `skill_ids`),
`POST /candidate/resume/draft` (поле `parsed.skill_ids`),
`GET /employer/vacancies/:id/candidates` (поле `skills` карточки).
"""

import io
from datetime import date
from decimal import Decimal
from itertools import count
from typing import Iterator

import pytest
import pytest_asyncio
from docx import Document
from httpx import AsyncClient

from app.ai.service import ai_service
from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import ApplicationStatus, UserRole, VacancyStatus
from app.skills.models import Skill, SkillAlias
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(940000)
_candidate_ids = count(941000)

FULL_PROFILE = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": "70000",
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": "2026-10-01",
}


class _FakeTextProvider:
    def __init__(self, name: str, response: str = "{}") -> None:
        self.name = name
        self._response = response

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return self._response


@pytest.fixture(autouse=True)
def _reset_ai_providers() -> Iterator[None]:
    yield
    ai_service.set_providers(text_providers=[], speech_providers=[])


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    yield
    await Vacancy.filter(employer_id__gte=940000, employer_id__lt=941000).delete()
    await Skill.filter(
        name__in=("Тестовый навык 1", "Тестовый навык 2", "Microsoft Excel (тест)")
    ).delete()


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _candidate(client: AsyncClient) -> User:
    return await _login(client, next(_candidate_ids), UserRole.CANDIDATE)


async def _skill(name: str) -> Skill:
    skill, _ = await Skill.get_or_create(name=name)
    return skill


async def _alias(alias: str, skill: Skill) -> SkillAlias:
    row, _ = await SkillAlias.get_or_create(alias=alias, skill=skill)
    return row


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --- Справочник --------------------------------------------------------------


async def test_list_skills_requires_auth_and_supports_search(
    client: AsyncClient,
) -> None:
    guest = await client.get("/api/skills")
    assert guest.status_code == 401

    first = await _skill("Тестовый навык 1")
    await _skill("Тестовый навык 2")
    await _candidate(client)

    everything = await client.get("/api/skills")
    assert everything.status_code == 200, everything.text
    names = {item["name"] for item in everything.json()["items"]}
    assert {"Тестовый навык 1", "Тестовый навык 2"} <= names

    filtered = await client.get("/api/skills", params={"query": "навык 1"})
    assert [item["id"] for item in filtered.json()["items"]] == [first.id]


async def test_list_skills_search_matches_aliases(client: AsyncClient) -> None:
    """Приложение A справочника: «Эксель»/«Excel» должны находить канонический
    навык, даже если запрос не совпадает с его названием буквально."""
    canonical = await _skill("Microsoft Excel (тест)")
    await _alias("Эксель (тест)", canonical)
    await _candidate(client)

    found = await client.get("/api/skills", params={"query": "Эксель (тест)"})
    assert found.status_code == 200, found.text
    assert [item["id"] for item in found.json()["items"]] == [canonical.id]


# --- Сохранение в профиле -----------------------------------------------------


async def test_profile_skill_ids_happy_path_and_validation(
    client: AsyncClient,
) -> None:
    skill_a = await _skill("Тестовый навык 1")
    skill_b = await _skill("Тестовый навык 2")
    await _candidate(client)

    # 1. Неизвестный id отклоняется, профиль не создаётся с мусором
    unknown = await client.patch(
        "/api/candidate/profile",
        json={**FULL_PROFILE, "skill_ids": [999999999]},
    )
    assert unknown.status_code == 422, unknown.text
    assert unknown.json()["error"]["code"] == "unknown_skill_id"

    # 2. Дубли схлопываются, порядок первого вхождения сохраняется
    created = await client.patch(
        "/api/candidate/profile",
        json={**FULL_PROFILE, "skill_ids": [skill_b.id, skill_a.id, skill_b.id]},
    )
    assert created.status_code == 200, created.text
    assert [item["id"] for item in created.json()["skills"]] == [skill_b.id, skill_a.id]
    assert {item["name"] for item in created.json()["skills"]} == {
        "Тестовый навык 1",
        "Тестовый навык 2",
    }

    # 3. GET отдаёт то же самое — сохранилось по-настоящему
    stored = await client.get("/api/candidate/profile")
    assert stored.json()["skills"] == created.json()["skills"]

    # 4. Явный null снимает все навыки (не 422 — колонка это допускает)
    cleared = await client.patch(
        "/api/candidate/profile", json={"skill_ids": None}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["skills"] == []

    # 5. Профиль без skill_ids вообще — навыков не было и нет (регрессия)
    await _candidate(client)
    fresh = await client.patch("/api/candidate/profile", json=FULL_PROFILE)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["skills"] == []


async def test_profile_skill_ids_too_many_rejected(client: AsyncClient) -> None:
    await _candidate(client)
    too_many = await client.patch(
        "/api/candidate/profile",
        json={**FULL_PROFILE, "skill_ids": list(range(1, 32))},
    )
    assert too_many.status_code == 422, too_many.text


# --- Подсказка из резюме ------------------------------------------------------


async def test_resume_suggests_skills_found_in_text(client: AsyncClient) -> None:
    skill = await _skill("Тестовый навык 1")
    await _skill("Тестовый навык 2")
    await _candidate(client)

    ai_service.set_providers(text_providers=[_FakeTextProvider("gigachat")])

    response = await client.post(
        "/api/candidate/resume/draft",
        files={
            "file": (
                "resume.docx",
                _docx_bytes(["Работал бариста", "Владею: Тестовый навык 1"]),
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["parsed"]["skill_ids"] == [skill.id]


async def test_resume_suggests_skills_via_alias(client: AsyncClient) -> None:
    """Резюме может упоминать разговорный вариант («Эксель»), а не
    канонический («Microsoft Excel») — подсказка должна найти его по
    справочнику алиасов (приложение A), не только по точному названию."""
    canonical = await _skill("Microsoft Excel (тест)")
    await _alias("Эксель (тест)", canonical)
    await _candidate(client)

    ai_service.set_providers(text_providers=[_FakeTextProvider("gigachat")])

    response = await client.post(
        "/api/candidate/resume/draft",
        files={
            "file": (
                "resume.docx",
                _docx_bytes(["Уверенно работаю в Эксель (тест) каждый день"]),
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["parsed"]["skill_ids"] == [canonical.id]


# --- Карточка работодателя -----------------------------------------------


async def test_employer_candidate_card_shows_resolved_skills(
    client: AsyncClient,
) -> None:
    skill_a = await _skill("Тестовый навык 1")
    skill_b = await _skill("Тестовый навык 2")

    employer = await _login(client, next(_employer_ids), UserRole.EMPLOYER)
    vacancy = await Vacancy.create(
        employer=employer,
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )

    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await CandidateProfile.create(
        user_id=candidate.user_id,
        desired_role="Бариста",
        city="Москва",
        salary=Decimal("70000"),
        schedule="full_time",
        experience_months=24,
        available_from=date(2026, 10, 1),
        skill_ids=[skill_a.id, skill_b.id],
    )
    await Application.create(
        vacancy=vacancy, candidate=candidate, status=ApplicationStatus.PASSED
    )

    await _login(client, employer.user_id, UserRole.EMPLOYER)
    candidates = await client.get(f"/api/employer/vacancies/{vacancy.id}/candidates")
    assert candidates.status_code == 200, candidates.text
    card = candidates.json()["items"][0]
    assert {item["name"] for item in card["skills"]} == {
        "Тестовый навык 1",
        "Тестовый навык 2",
    }
