"""POST /candidate/resume/draft. Экран C11 UX-карты, функция 29.

Отдельный файл, а не часть `test_candidate_profile.py`: это ровно тот путь,
которого раньше не было — разбор резюме без уже созданного профиля. Основной
`PATCH /candidate/resume` (требующий профиль) отдельных тестов пока не имеет
и не входит в эту правку.
"""

import io
from itertools import count
from typing import Iterator

import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient

from app.ai.service import ai_service
from app.candidates.models import CandidateProfile
from app.core.enums import UserRole
from app.main import app
from app.users.models import User
from tests.factories import build_init_data, max_user_payload

_candidate_ids = count(970000)
_employer_ids = count(971000)


class _FakeTextProvider:
    def __init__(self, name: str, response: str) -> None:
        self.name = name
        self._response = response

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return self._response


@pytest.fixture(autouse=True)
def _reset_ai_providers() -> Iterator[None]:
    """Провайдеры ИИ — общий singleton процесса: не должны утекать в другие тесты."""
    yield
    ai_service.set_providers(text_providers=[], speech_providers=[])


def _fresh_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, user_id: int, role: UserRole | None) -> None:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    if role is not None:
        await User.filter(user_id=user_id).update(role=role)


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_resume_draft_works_without_existing_profile(client: AsyncClient) -> None:
    """Главный сценарий: у кандидата ещё нет строки в `candidate_profiles`,
    но разбор резюме уже отвечает 200, а не 404 `candidate_profile_not_found`."""
    user_id = next(_candidate_ids)
    await _login(client, user_id, UserRole.CANDIDATE)
    assert await CandidateProfile.get_or_none(user_id=user_id) is None

    ai_service.set_providers(
        text_providers=[
            _FakeTextProvider(
                "gigachat",
                response='{"desired_role": "Бариста", "city": "Москва"}',
            )
        ]
    )

    response = await client.post(
        "/api/candidate/resume/draft",
        files={
            "file": (
                "resume.docx",
                _docx_bytes(["Иван Иванов", "Бариста, Москва"]),
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_available"] is True
    assert body["provider"] == "gigachat"
    assert body["parsed"]["desired_role"] == "Бариста"
    assert body["parsed"]["city"] == "Москва"

    # Вызов ничего не сохраняет: профиля по-прежнему нет
    assert await CandidateProfile.get_or_none(user_id=user_id) is None


async def test_resume_draft_empty_document_returns_empty_draft(
    client: AsyncClient,
) -> None:
    """Файл валиден, но текста в нём нет — пустой черновик, а не ошибка."""
    user_id = next(_candidate_ids)
    await _login(client, user_id, UserRole.CANDIDATE)
    ai_service.set_providers(
        text_providers=[_FakeTextProvider("gigachat", response="{}")]
    )

    response = await client.post(
        "/api/candidate/resume/draft",
        files={
            "file": (
                "resume.docx",
                _docx_bytes([]),
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_available"] is False
    assert body["provider"] is None
    assert body["parsed"] == {
        "desired_role": None,
        "city": None,
        "salary": None,
        "schedule": None,
        "experience_months": None,
        "available_from": None,
        "skill_ids": [],
    }


async def test_resume_draft_rejects_empty_file(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    response = await client.post(
        "/api/candidate/resume/draft",
        files={"file": ("resume.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_file"


async def test_resume_draft_rejects_unsupported_file_type(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    response = await client.post(
        "/api/candidate/resume/draft",
        files={"file": ("resume.txt", b"not a real resume", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


async def test_resume_draft_access_control(client: AsyncClient) -> None:
    async with _fresh_client() as guest:
        response = await guest.post(
            "/api/candidate/resume/draft",
            files={"file": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert response.status_code == 401

    await _login(client, next(_employer_ids), UserRole.EMPLOYER)
    wrong_role = await client.post(
        "/api/candidate/resume/draft",
        files={"file": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"
