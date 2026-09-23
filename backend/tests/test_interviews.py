"""Слоты собеседований и бронирование.

`POST /api/vacancies/{id}/slots`, `GET /api/vacancies/{id}/slots`,
`DELETE /api/vacancies/{id}/slots/{slot_id}`, `POST /api/matches/{id}/book`.
Разделы 22, 23, 26, 36, 37, 56, 57, 79 тех-доки.
"""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications.models import Application, Match
from app.candidates.models import CandidateProfile
from app.core.database import utcnow
from app.core.enums import (
    ApplicationStatus,
    InterviewSlotStatus,
    InterviewStatus,
    UserRole,
    VacancyStatus,
)
from app.interviews.models import Interview, InterviewSlot
from app.main import app
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload

_employer_ids = count(760000)
_candidate_ids = count(761000)

FITTING_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
    "available_from": date(2026, 10, 1),
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    """Вакансии модуля не должны попадать в ленту соседних тестов.

    Собеседования удаляются первыми: `interviews.slot_id` защищён `RESTRICT`,
    и каскад от вакансии к слоту сам по себе не пройдёт.
    """
    yield
    vacancy_ids = await Vacancy.filter(
        employer_id__gte=760000, employer_id__lt=761000
    ).values_list("id", flat=True)
    if not vacancy_ids:
        return
    slot_ids = await InterviewSlot.filter(vacancy_id__in=vacancy_ids).values_list(
        "id", flat=True
    )
    if slot_ids:
        await Interview.filter(slot_id__in=slot_ids).delete()
    await Vacancy.filter(id__in=vacancy_ids).delete()


# --- Вспомогательные функции ------------------------------------------------


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _employer(client: AsyncClient) -> User:
    """Работодатель, залогиненный в текущем клиенте."""
    return await _login(client, next(_employer_ids), UserRole.EMPLOYER)


async def _other_employer() -> User:
    return await User.create(
        user_id=next(_employer_ids), first_name="Другой", role=UserRole.EMPLOYER
    )


async def _vacancy(employer: User) -> Vacancy:
    return await Vacancy.create(
        employer=employer,
        title="Бариста в центре",
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )


async def _candidate() -> User:
    candidate = await User.create(
        user_id=next(_candidate_ids), first_name="Кандидат", role=UserRole.CANDIDATE
    )
    await CandidateProfile.create(user_id=candidate.user_id, **FITTING_PROFILE)
    return candidate


async def _application(
    vacancy: Vacancy,
    candidate: User,
    *,
    status: ApplicationStatus = ApplicationStatus.MUTUAL_INTEREST,
) -> Application:
    return await Application.create(vacancy=vacancy, candidate=candidate, status=status)


async def _matched(
    vacancy: Vacancy, candidate: User | None = None
) -> tuple[Match, Application, User]:
    """Взаимный интерес по вакансии.

    Отклик и match создаются напрямую: путь до них проверяет
    `test_employer_decision`, здесь важно то, что начинается после.
    """
    candidate = candidate or await _candidate()
    application = await _application(vacancy, candidate)
    match = await Match.create(application_id=application.id)
    return match, application, candidate


def _at(*, hours: float = 0, days: float = 0) -> datetime:
    """Момент в будущем относительно текущего времени."""
    return utcnow() + timedelta(hours=hours, days=days)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


async def _create_slot(
    client: AsyncClient, vacancy: Vacancy, *, starts_at: datetime, ends_at: datetime
):
    return await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={"starts_at": _iso(starts_at), "ends_at": _iso(ends_at)},
    )


async def _slot(
    vacancy: Vacancy,
    employer: User,
    *,
    starts_at: datetime | None = None,
    duration_minutes: int = 60,
    status: InterviewSlotStatus = InterviewSlotStatus.AVAILABLE,
) -> InterviewSlot:
    """Слот напрямую в БД — там, где проверяется не создание, а его следствия."""
    starts_at = starts_at or _at(days=1)
    return await InterviewSlot.create(
        employer_id=employer.user_id,
        vacancy_id=vacancy.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=duration_minutes),
        status=status,
    )


async def _list_slots(client: AsyncClient, vacancy: Vacancy):
    return await client.get(f"/api/vacancies/{vacancy.id}/slots")


async def _cancel_slot(client: AsyncClient, vacancy: Vacancy, slot_id: int):
    return await client.delete(f"/api/vacancies/{vacancy.id}/slots/{slot_id}")


async def _book(client: AsyncClient, match: Match, slot_id: int):
    return await client.post(
        f"/api/matches/{match.id}/book", json={"slot_id": slot_id}
    )


def _fresh_client() -> AsyncClient:
    """Отдельная сессия: у двух кандидатов не может быть общей cookie."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Создание слота ---------------------------------------------------------


async def test_slot_creation_requires_session(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)

    response = await _create_slot(
        client, vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )

    assert response.status_code == 401


async def test_candidate_cannot_create_slot(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _create_slot(
        client, vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_slot_cannot_be_created_for_foreign_vacancy(
    client: AsyncClient,
) -> None:
    vacancy = await _vacancy(await _other_employer())
    await _employer(client)

    response = await _create_slot(
        client, vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"
    assert not await InterviewSlot.filter(vacancy_id=vacancy.id).exists()


async def test_slot_is_created(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)

    response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == InterviewSlotStatus.AVAILABLE.value

    slot = await InterviewSlot.get(id=body["id"])
    # Работодатель берётся из сессии, а не из тела запроса
    assert slot.employer_id == employer.user_id
    assert slot.starts_at == starts_at
    assert slot.ends_at == starts_at + timedelta(hours=1)


async def test_slot_without_timezone_is_rejected(client: AsyncClient) -> None:
    """Без смещения непонятно, в каком поясе назначено собеседование."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    response = await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={"starts_at": "2026-10-01T10:00:00", "ends_at": "2026-10-01T11:00:00"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_slot_with_offset_is_stored_in_utc(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    moscow_day = (utcnow() + timedelta(days=2)).strftime("%Y-%m-%d")

    response = await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={
            "starts_at": f"{moscow_day}T12:00:00+03:00",
            "ends_at": f"{moscow_day}T13:00:00+03:00",
        },
    )

    assert response.status_code == 201, response.text
    slot = await InterviewSlot.get(id=response.json()["id"])
    assert slot.starts_at.hour == 9
    assert slot.starts_at.utcoffset() == timedelta(0)


async def test_slot_ending_before_start_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)

    response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at - timedelta(minutes=30)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "slot_interval_invalid"


async def test_slot_in_past_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = utcnow() - timedelta(hours=2)

    response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "slot_in_past"


async def test_too_short_and_too_long_slots_are_rejected(
    client: AsyncClient,
) -> None:
    """Границы длительности вне тех-доки и заданы конфигурацией."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)

    short = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=1)
    )
    long = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=9)
    )

    assert short.status_code == 422
    assert short.json()["error"]["code"] == "slot_too_short"
    assert long.status_code == 422
    assert long.json()["error"]["code"] == "slot_too_long"
    assert not await InterviewSlot.filter(vacancy_id=vacancy.id).exists()


async def test_overlapping_slot_is_rejected(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    first = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert first.status_code == 201, first.text

    response = await _create_slot(
        client,
        vacancy,
        starts_at=starts_at + timedelta(minutes=30),
        ends_at=starts_at + timedelta(minutes=90),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_overlaps"
    assert response.json()["error"]["details"]["slot_id"] == first.json()["id"]
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 1


async def test_overlap_is_checked_across_employer_vacancies(
    client: AsyncClient,
) -> None:
    """Работодатель не может вести два собеседования одновременно."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    other_vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    assert (
        await _create_slot(
            client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
        )
    ).status_code == 201

    response = await _create_slot(
        client,
        other_vacancy,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_overlaps"


async def test_slots_of_other_employer_do_not_block(client: AsyncClient) -> None:
    other = await _other_employer()
    other_vacancy = await _vacancy(other)
    starts_at = _at(days=1)
    await _slot(other_vacancy, other, starts_at=starts_at)
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )

    assert response.status_code == 201, response.text


async def test_adjacent_slots_are_allowed(client: AsyncClient) -> None:
    """Слот, начинающийся ровно в момент окончания предыдущего, не пересекается."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    assert (
        await _create_slot(
            client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
        )
    ).status_code == 201

    response = await _create_slot(
        client,
        vacancy,
        starts_at=starts_at + timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=2),
    )

    assert response.status_code == 201, response.text
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 2


async def test_cancelled_slot_does_not_block_new_one(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    await _slot(
        vacancy, employer, starts_at=starts_at, status=InterviewSlotStatus.CANCELLED
    )

    response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )

    assert response.status_code == 201, response.text


async def test_concurrent_overlapping_slots_produce_one(client: AsyncClient) -> None:
    """Проверка пересечения и вставка идут под одной блокировкой."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)

    responses = await asyncio.gather(
        *[
            _create_slot(
                client,
                vacancy,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
            )
            for _ in range(4)
        ]
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409, 409, 409]
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 1


# --- Чтение слотов ----------------------------------------------------------


async def test_employer_sees_own_slots_including_booked(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    later = await _slot(vacancy, employer, starts_at=_at(days=2))
    earlier = await _slot(
        vacancy, employer, starts_at=_at(days=1), status=InterviewSlotStatus.BOOKED
    )
    await _slot(
        vacancy, employer, starts_at=_at(days=3), status=InterviewSlotStatus.CANCELLED
    )

    body = (await _list_slots(client, vacancy)).json()

    # Отменённые слоты не показываются, порядок — по времени начала
    assert [item["id"] for item in body["items"]] == [earlier.id, later.id]
    assert body["items"][0]["status"] == InterviewSlotStatus.BOOKED.value
    assert body["match_id"] is None


async def test_employer_does_not_see_foreign_slots(client: AsyncClient) -> None:
    other = await _other_employer()
    vacancy = await _vacancy(other)
    await _slot(vacancy, other)
    await _employer(client)

    response = await _list_slots(client, vacancy)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_candidate_without_match_cannot_see_slots(
    client: AsyncClient,
) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    await _slot(vacancy, employer)
    candidate = await _candidate()
    await _application(vacancy, candidate, status=ApplicationStatus.PASSED)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _list_slots(client, vacancy)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "match_required"


async def test_candidate_sees_only_free_future_slots(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    free = await _slot(vacancy, employer, starts_at=_at(days=1))
    await _slot(
        vacancy, employer, starts_at=_at(days=2), status=InterviewSlotStatus.BOOKED
    )
    await _slot(
        vacancy, employer, starts_at=_at(days=3), status=InterviewSlotStatus.CANCELLED
    )
    await _slot(vacancy, employer, starts_at=utcnow() - timedelta(hours=1))
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    body = (await _list_slots(client, vacancy)).json()

    assert [item["id"] for item in body["items"]] == [free.id]
    assert body["match_id"] == match.id
    assert body["interviews"] == []


async def test_candidate_slot_view_is_logged(client: AsyncClient) -> None:
    """Раздел 60: `slot_viewed`."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    await _slot(vacancy, employer)
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    await _list_slots(client, vacancy)

    event = await AnalyticsEvent.filter(
        user_id=candidate.user_id, event_name="slot_viewed"
    ).get()
    assert event.payload == {
        "vacancy_id": vacancy.id,
        "match_id": match.id,
        "slots": 1,
    }


async def test_slots_of_unknown_vacancy_return_404(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await client.get("/api/vacancies/999999/slots")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vacancy_not_found"


async def test_slots_require_selected_role(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    user_id = next(_candidate_ids)
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )

    response = await _list_slots(client, vacancy)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_selected"


# --- Отмена слота -----------------------------------------------------------


async def test_slot_is_cancelled_and_hidden(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)

    response = await _cancel_slot(client, vacancy, slot.id)

    assert response.status_code == 204
    await slot.refresh_from_db()
    assert slot.status is InterviewSlotStatus.CANCELLED
    assert (await _list_slots(client, vacancy)).json()["items"] == []


async def test_repeated_cancel_is_not_an_error(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer, status=InterviewSlotStatus.CANCELLED)

    assert (await _cancel_slot(client, vacancy, slot.id)).status_code == 204


async def test_booked_slot_cannot_be_cancelled(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer, status=InterviewSlotStatus.BOOKED)

    response = await _cancel_slot(client, vacancy, slot.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_booked"
    await slot.refresh_from_db()
    assert slot.status is InterviewSlotStatus.BOOKED


async def test_foreign_slot_cannot_be_cancelled(client: AsyncClient) -> None:
    other = await _other_employer()
    foreign_vacancy = await _vacancy(other)
    foreign_slot = await _slot(foreign_vacancy, other)
    employer = await _employer(client)
    own_vacancy = await _vacancy(employer)

    by_own_vacancy = await _cancel_slot(client, own_vacancy, foreign_slot.id)
    by_foreign_vacancy = await _cancel_slot(client, foreign_vacancy, foreign_slot.id)

    assert by_own_vacancy.status_code == 404
    assert by_own_vacancy.json()["error"]["code"] == "slot_not_found"
    assert by_foreign_vacancy.status_code == 404
    assert by_foreign_vacancy.json()["error"]["code"] == "vacancy_not_found"
    await foreign_slot.refresh_from_db()
    assert foreign_slot.status is InterviewSlotStatus.AVAILABLE


async def test_candidate_cannot_cancel_slot(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _cancel_slot(client, vacancy, slot.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


# --- Бронирование -----------------------------------------------------------


async def test_booking_creates_interview_and_moves_application(
    client: AsyncClient,
) -> None:
    """Раздел 56: слот занят, собеседование создано, отклик переведён."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, application, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _book(client, match, slot.id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["match_id"] == match.id
    assert body["application_id"] == application.id
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == InterviewStatus.SCHEDULED.value
    assert body["application_status"] == ApplicationStatus.INTERVIEW_SCHEDULED.value
    assert body["slot"]["id"] == slot.id
    assert body["slot"]["status"] == InterviewSlotStatus.BOOKED.value

    await slot.refresh_from_db()
    assert slot.status is InterviewSlotStatus.BOOKED
    await application.refresh_from_db()
    assert application.status is ApplicationStatus.INTERVIEW_SCHEDULED
    interview = await Interview.get(match_id=match.id)
    assert interview.slot_id == slot.id


async def test_booking_is_idempotent(client: AsyncClient) -> None:
    """Раздел 79: повтор запроса не создаёт второе собеседование."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    first = await _book(client, match, slot.id)
    assert first.status_code == 201, first.text

    repeated = await _book(client, match, slot.id)

    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]
    assert await Interview.filter(match_id=match.id).count() == 1


async def test_booking_another_slot_after_booking_is_refused(
    client: AsyncClient,
) -> None:
    """Перенос собеседования — P1 (раздел 46)."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer, starts_at=_at(days=1))
    other_slot = await _slot(vacancy, employer, starts_at=_at(days=2))
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    assert (await _book(client, match, slot.id)).status_code == 201

    response = await _book(client, match, other_slot.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interview_already_scheduled"
    await other_slot.refresh_from_db()
    assert other_slot.status is InterviewSlotStatus.AVAILABLE


async def test_taken_slot_cannot_be_booked_twice(client: AsyncClient) -> None:
    """Раздел 57: занятый слот — `409 Conflict`."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    first_match, _, first_candidate = await _matched(vacancy)
    second_match, second_application, second_candidate = await _matched(vacancy)
    await _login(client, first_candidate.user_id, UserRole.CANDIDATE)
    assert (await _book(client, first_match, slot.id)).status_code == 201
    await _login(client, second_candidate.user_id, UserRole.CANDIDATE)

    response = await _book(client, second_match, slot.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_taken"
    assert await Interview.filter(slot_id=slot.id).count() == 1
    await second_application.refresh_from_db()
    assert second_application.status is ApplicationStatus.MUTUAL_INTEREST


async def test_concurrent_booking_of_one_slot(client: AsyncClient) -> None:
    """Два кандидата одновременно: слот достаётся одному."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    first_match, _, first_candidate = await _matched(vacancy)
    second_match, _, second_candidate = await _matched(vacancy)

    async with _fresh_client() as first_client, _fresh_client() as second_client:
        await _login(first_client, first_candidate.user_id, UserRole.CANDIDATE)
        await _login(second_client, second_candidate.user_id, UserRole.CANDIDATE)

        responses = await asyncio.gather(
            _book(first_client, first_match, slot.id),
            _book(second_client, second_match, slot.id),
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert await Interview.filter(slot_id=slot.id).count() == 1
    assert (
        await Application.filter(
            vacancy_id=vacancy.id, status=ApplicationStatus.INTERVIEW_SCHEDULED
        ).count()
        == 1
    )


async def test_cancelled_and_past_slots_cannot_be_booked(
    client: AsyncClient,
) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    cancelled = await _slot(
        vacancy, employer, starts_at=_at(days=1), status=InterviewSlotStatus.CANCELLED
    )
    past = await _slot(vacancy, employer, starts_at=utcnow() - timedelta(hours=1))
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    cancelled_response = await _book(client, match, cancelled.id)
    past_response = await _book(client, match, past.id)

    assert cancelled_response.status_code == 409
    assert cancelled_response.json()["error"]["code"] == "slot_cancelled"
    assert past_response.status_code == 409
    assert past_response.json()["error"]["code"] == "slot_in_past"
    assert not await Interview.filter(match_id=match.id).exists()


async def test_slot_of_other_vacancy_cannot_be_booked(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    other_vacancy = await _vacancy(employer)
    foreign_slot = await _slot(other_vacancy, employer)
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _book(client, match, foreign_slot.id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "slot_not_found"


async def test_unknown_slot_is_not_found(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _book(client, match, 999999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "slot_not_found"


async def test_foreign_match_cannot_be_booked(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, application, _ = await _matched(vacancy)
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await _book(client, match, slot.id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "match_not_found"
    await application.refresh_from_db()
    assert application.status is ApplicationStatus.MUTUAL_INTEREST


async def test_unknown_match_is_not_found(client: AsyncClient) -> None:
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)

    response = await client.post("/api/matches/999999/book", json={"slot_id": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "match_not_found"


async def test_booking_requires_candidate_role(client: AsyncClient) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, _, _ = await _matched(vacancy)

    response = await _book(client, match, slot.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_role"


async def test_booking_requires_session(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, _, _ = await _matched(vacancy)

    assert (await _book(client, match, slot.id)).status_code == 401


async def test_booking_before_mutual_interest_is_refused(
    client: AsyncClient,
) -> None:
    """Статус отклика проверяется по карте переходов раздела 26."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    candidate = await _candidate()
    application = await _application(
        vacancy, candidate, status=ApplicationStatus.PASSED
    )
    match = await Match.create(application_id=application.id)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    response = await _book(client, match, slot.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
    await slot.refresh_from_db()
    assert slot.status is InterviewSlotStatus.AVAILABLE


async def test_booking_writes_analytics_event(client: AsyncClient) -> None:
    """Раздел 60: `interview_booked`."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, application, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)

    interview_id = (await _book(client, match, slot.id)).json()["id"]

    event = await AnalyticsEvent.filter(
        user_id=candidate.user_id, event_name="interview_booked"
    ).get()
    assert event.payload == {
        "interview_id": interview_id,
        "match_id": match.id,
        "application_id": application.id,
        "vacancy_id": vacancy.id,
        "slot_id": slot.id,
    }


async def test_candidate_sees_booked_interview_after_reload(
    client: AsyncClient,
) -> None:
    """Экран «Интервью назначено» восстанавливается из состояния на сервере."""
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer, starts_at=_at(days=1))
    free_slot = await _slot(vacancy, employer, starts_at=_at(days=2))
    match, _, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    await _book(client, match, slot.id)

    body = (await _list_slots(client, vacancy)).json()

    # Занятый слот в выбор больше не попадает, а назначенное время видно
    assert [item["id"] for item in body["items"]] == [free_slot.id]
    assert len(body["interviews"]) == 1
    interview = body["interviews"][0]
    assert interview["slot"]["id"] == slot.id
    assert interview["status"] == InterviewStatus.SCHEDULED.value
    assert (
        interview["application_status"]
        == ApplicationStatus.INTERVIEW_SCHEDULED.value
    )


async def test_cancel_and_booking_race_leaves_consistent_state(
    client: AsyncClient,
) -> None:
    """Работодатель снимает время ровно тогда, когда кандидат его выбирает.

    Оба запроса блокируют один и тот же слот, поэтому побеждает один: либо
    слот отменён и собеседования нет, либо собеседование назначено, а отмена
    отклонена. Промежуточного состояния быть не должно.
    """
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, application, candidate = await _matched(vacancy)

    async with _fresh_client() as candidate_client:
        await _login(candidate_client, candidate.user_id, UserRole.CANDIDATE)

        cancelled, booked = await asyncio.gather(
            _cancel_slot(client, vacancy, slot.id),
            _book(candidate_client, match, slot.id),
        )

    await slot.refresh_from_db()
    await application.refresh_from_db()
    if cancelled.status_code == 204:
        assert booked.status_code == 409
        assert booked.json()["error"]["code"] == "slot_cancelled"
        assert slot.status is InterviewSlotStatus.CANCELLED
        assert application.status is ApplicationStatus.MUTUAL_INTEREST
        assert not await Interview.filter(match_id=match.id).exists()
    else:
        assert booked.status_code == 201, booked.text
        assert cancelled.status_code == 409
        assert cancelled.json()["error"]["code"] == "slot_booked"
        assert slot.status is InterviewSlotStatus.BOOKED
        assert application.status is ApplicationStatus.INTERVIEW_SCHEDULED


# --- Сквозной путь этапа ----------------------------------------------------


async def test_invite_to_interview_scheduled(client: AsyncClient) -> None:
    """Приглашение → взаимный интерес → слот → бронирование → назначено.

    Результат обязательного маршрута P0 (раздел 1): `Interview scheduled`.
    """
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    candidate = await _candidate()
    application = await _application(
        vacancy, candidate, status=ApplicationStatus.PASSED
    )

    decision = await client.post(
        f"/api/applications/{application.id}/decision", json={"action": "invited"}
    )
    assert decision.status_code == 200, decision.text
    match_id = decision.json()["match_id"]

    starts_at = _at(days=1)
    slot = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert slot.status_code == 201, slot.text
    slot_id = slot.json()["id"]

    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    available = (await _list_slots(client, vacancy)).json()
    assert [item["id"] for item in available["items"]] == [slot_id]
    assert available["match_id"] == match_id

    booked = await client.post(
        f"/api/matches/{match_id}/book", json={"slot_id": slot_id}
    )

    assert booked.status_code == 201, booked.text
    await application.refresh_from_db()
    assert application.status is ApplicationStatus.INTERVIEW_SCHEDULED
    interview = await Interview.get(match_id=match_id)
    assert interview.status is InterviewStatus.SCHEDULED
    assert (await InterviewSlot.get(id=slot_id)).status is InterviewSlotStatus.BOOKED


async def test_employer_sees_scheduled_interviews(client: AsyncClient) -> None:
    """Работодателю нужно не только «слот занят», но и с кем встреча."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer, starts_at=_at(days=1))
    await _slot(vacancy, employer, starts_at=_at(days=2))
    match, application, candidate = await _matched(vacancy)

    async with _fresh_client() as candidate_client:
        await _login(candidate_client, candidate.user_id, UserRole.CANDIDATE)
        assert (await _book(candidate_client, match, slot.id)).status_code == 201

    body = (await _list_slots(client, vacancy)).json()

    assert len(body["interviews"]) == 1
    interview = body["interviews"][0]
    assert interview["application_id"] == application.id
    assert interview["match_id"] == match.id
    assert interview["slot"]["id"] == slot.id
    assert interview["status"] == InterviewStatus.SCHEDULED.value
    # Личных данных кандидата в ответе нет (раздел 34)
    assert "Кандидат" not in str(body)


async def test_candidate_does_not_see_other_interviews(client: AsyncClient) -> None:
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    taken_slot = await _slot(vacancy, employer, starts_at=_at(days=1))
    await _slot(vacancy, employer, starts_at=_at(days=2))
    other_match, other_application, other_candidate = await _matched(vacancy)
    match, _, candidate = await _matched(vacancy)

    async with _fresh_client() as other_client:
        await _login(other_client, other_candidate.user_id, UserRole.CANDIDATE)
        booked = await _book(other_client, other_match, taken_slot.id)
        assert booked.status_code == 201, booked.text

    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    body = (await _list_slots(client, vacancy)).json()

    assert body["match_id"] == match.id
    assert body["interviews"] == []
    assert str(other_application.id) not in str(body["interviews"])
