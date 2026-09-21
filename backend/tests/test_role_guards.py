"""Ограничения по роли. Разделы 11, 12: без роли бизнес-операции запрещены."""

import pytest

from app.auth.dependencies import require_candidate, require_employer
from app.core.enums import UserRole
from app.core.errors import ForbiddenError
from app.users.models import User


def _user(role: UserRole | None) -> User:
    return User(user_id=720001, first_name="Тест", role=role)


async def test_user_without_role_is_blocked() -> None:
    with pytest.raises(ForbiddenError) as candidate_error:
        await require_candidate(_user(None))
    with pytest.raises(ForbiddenError) as employer_error:
        await require_employer(_user(None))

    assert candidate_error.value.code == "role_not_selected"
    assert employer_error.value.code == "role_not_selected"


async def test_candidate_cannot_use_employer_endpoints() -> None:
    with pytest.raises(ForbiddenError) as error:
        await require_employer(_user(UserRole.CANDIDATE))

    assert error.value.code == "wrong_role"


async def test_employer_cannot_use_candidate_endpoints() -> None:
    with pytest.raises(ForbiddenError) as error:
        await require_candidate(_user(UserRole.EMPLOYER))

    assert error.value.code == "wrong_role"


async def test_matching_role_passes() -> None:
    candidate = _user(UserRole.CANDIDATE)
    employer = _user(UserRole.EMPLOYER)

    assert await require_candidate(candidate) is candidate
    assert await require_employer(employer) is employer
