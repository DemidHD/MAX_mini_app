"""Проверки схемы БД: ключи и ограничения из разделов 8, 17, 19, 21, 55."""

from datetime import timedelta

import pytest
from tortoise.exceptions import IntegrityError

from app.applications.models import Application, Match, ScreeningAnswer
from app.candidates.models import CandidateProfile
from app.core.database import utcnow
from app.core.enums import (
    ApplicationStatus,
    ScreeningQuestionType,
    UserRole,
    VacancyStatus,
)
from app.interviews.models import Interview, InterviewSlot
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy


async def _employer(user_id: int) -> User:
    return await User.create(user_id=user_id, first_name="Работодатель")


async def _candidate(user_id: int) -> User:
    return await User.create(
        user_id=user_id, first_name="Кандидат", role=UserRole.CANDIDATE
    )


async def test_user_id_is_supplied_by_max_and_role_starts_empty() -> None:
    user = await User.create(user_id=987654321, first_name="Иван", last_name="Петров")

    stored = await User.get(user_id=987654321)
    assert stored.pk == user.user_id == 987654321
    # Авторизация роль не назначает (раздел 8)
    assert stored.role is None


async def test_candidate_profile_is_one_to_one_with_user() -> None:
    user = await _candidate(1001)
    await CandidateProfile.create(user=user, desired_role="Бариста", city="Москва")

    with pytest.raises(IntegrityError):
        await CandidateProfile.create(user=user, desired_role="Официант")


async def test_duplicate_application_is_rejected_by_constraint() -> None:
    employer = await _employer(2001)
    candidate = await _candidate(2002)
    vacancy = await Vacancy.create(
        employer=employer, title="Бариста", status=VacancyStatus.PUBLISHED
    )

    await Application.create(
        vacancy=vacancy, candidate=candidate, status=ApplicationStatus.SCREENING
    )

    with pytest.raises(IntegrityError):
        await Application.create(vacancy=vacancy, candidate=candidate)


async def test_one_answer_per_question_within_application() -> None:
    employer = await _employer(3001)
    candidate = await _candidate(3002)
    vacancy = await Vacancy.create(employer=employer, title="Официант")
    question = await ScreeningQuestion.create(
        vacancy=vacancy,
        question="Готовы работать в вечернюю смену?",
        type=ScreeningQuestionType.BOOLEAN,
        required=True,
        sort_order=1,
    )
    application = await Application.create(vacancy=vacancy, candidate=candidate)

    await ScreeningAnswer.create(
        application=application, question=question, value={"answer": True}
    )

    with pytest.raises(IntegrityError):
        await ScreeningAnswer.create(
            application=application, question=question, value={"answer": False}
        )


async def test_slot_cannot_host_two_interviews() -> None:
    employer = await _employer(4001)
    first_candidate = await _candidate(4002)
    second_candidate = await _candidate(4003)
    vacancy = await Vacancy.create(employer=employer, title="Администратор")
    slot = await InterviewSlot.create(
        employer=employer,
        vacancy=vacancy,
        starts_at=utcnow() + timedelta(days=1),
        ends_at=utcnow() + timedelta(days=1, hours=1),
    )

    first_match = await Match.create(
        application=await Application.create(vacancy=vacancy, candidate=first_candidate)
    )
    second_match = await Match.create(
        application=await Application.create(vacancy=vacancy, candidate=second_candidate)
    )

    await Interview.create(match=first_match, slot=slot)

    with pytest.raises(IntegrityError):
        await Interview.create(match=second_match, slot=slot)


async def test_match_is_unique_per_application() -> None:
    employer = await _employer(5001)
    candidate = await _candidate(5002)
    vacancy = await Vacancy.create(employer=employer, title="Повар")
    application = await Application.create(vacancy=vacancy, candidate=candidate)

    await Match.create(application=application)

    with pytest.raises(IntegrityError):
        await Match.create(application=application)
