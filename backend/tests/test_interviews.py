"""Слоты собеседований и бронирование.

`POST /api/vacancies/{id}/slots`, `GET /api/vacancies/{id}/slots`,
`DELETE /api/vacancies/{id}/slots/{slot_id}`, `POST /api/matches/{id}/book`.
Разделы 22, 23, 26, 36, 37, 56, 57, 79 тех-доки.

Guard'ы, валидация и happy path каждой ручки собраны в сквозные сценарии по
одной функции на группу — с пронумерованными шагами, как в `test_p0_e2e.py`.
Конкурентные и гоночные сценарии (`asyncio.gather`, два клиента наперегонки)
оставлены отдельными тестами: там диагностика конкретной гонки важнее
компактности.
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
    return await client.post(f"/api/matches/{match.id}/book", json={"slot_id": slot_id})


def _fresh_client() -> AsyncClient:
    """Отдельная сессия: у двух кандидатов не может быть общей cookie."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Создание слота: guard'ы и валидация -------------------------------------


async def test_slot_creation_guards_and_validation(client: AsyncClient) -> None:
    # 1. Без сессии, с чужой ролью и на чужую вакансию — создать нельзя
    foreign_owner = await _other_employer()
    foreign_vacancy = await _vacancy(foreign_owner)
    no_session = await _create_slot(
        client, foreign_vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )
    assert no_session.status_code == 401

    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    wrong_role = await _create_slot(
        client, foreign_vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    employer = await _employer(client)
    foreign = await _create_slot(
        client, foreign_vacancy, starts_at=_at(days=1), ends_at=_at(days=1, hours=1)
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "vacancy_not_found"
    assert not await InterviewSlot.filter(vacancy_id=foreign_vacancy.id).exists()

    # 2. Слот создаётся из данных сессии, а не тела запроса
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    created = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["vacancy_id"] == vacancy.id
    assert body["status"] == InterviewSlotStatus.AVAILABLE.value
    slot = await InterviewSlot.get(id=body["id"])
    assert slot.employer_id == employer.user_id
    assert slot.starts_at == starts_at
    assert slot.ends_at == starts_at + timedelta(hours=1)

    # 3. Без смещения часового пояса — отклонено
    no_timezone = await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={"starts_at": "2026-10-01T10:00:00", "ends_at": "2026-10-01T11:00:00"},
    )
    assert no_timezone.status_code == 422
    assert no_timezone.json()["error"]["code"] == "validation_error"

    # 4. Время со смещением приводится к UTC при сохранении
    moscow_day = (utcnow() + timedelta(days=2)).strftime("%Y-%m-%d")
    offset_response = await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={
            "starts_at": f"{moscow_day}T12:00:00+03:00",
            "ends_at": f"{moscow_day}T13:00:00+03:00",
        },
    )
    assert offset_response.status_code == 201, offset_response.text
    offset_slot = await InterviewSlot.get(id=offset_response.json()["id"])
    assert offset_slot.starts_at.hour == 9
    assert offset_slot.starts_at.utcoffset() == timedelta(0)

    # 5. Конец раньше начала и время в прошлом — отклонены
    ending_before_start = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at - timedelta(minutes=30)
    )
    assert ending_before_start.status_code == 422
    assert ending_before_start.json()["error"]["code"] == "slot_interval_invalid"

    past_starts_at = utcnow() - timedelta(hours=2)
    in_past = await _create_slot(
        client,
        vacancy,
        starts_at=past_starts_at,
        ends_at=past_starts_at + timedelta(hours=1),
    )
    assert in_past.status_code == 422
    assert in_past.json()["error"]["code"] == "slot_in_past"

    # 6. Границы длительности заданы конфигурацией: слишком короткий и
    # слишком длинный слот отклонены, ничего не создаётся
    duration_vacancy = await _vacancy(employer)
    duration_starts_at = _at(days=1)
    short = await _create_slot(
        client,
        duration_vacancy,
        starts_at=duration_starts_at,
        ends_at=duration_starts_at + timedelta(minutes=1),
    )
    long = await _create_slot(
        client,
        duration_vacancy,
        starts_at=duration_starts_at,
        ends_at=duration_starts_at + timedelta(hours=9),
    )
    assert short.status_code == 422
    assert short.json()["error"]["code"] == "slot_too_short"
    assert long.status_code == 422
    assert long.json()["error"]["code"] == "slot_too_long"
    assert not await InterviewSlot.filter(vacancy_id=duration_vacancy.id).exists()


# --- Создание слота: пересечения ---------------------------------------------


async def test_slot_overlap_rules(client: AsyncClient) -> None:
    # 1. Пересекающийся слот отклоняется с указанием, с каким слотом конфликт
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)
    first = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert first.status_code == 201, first.text
    overlapping = await _create_slot(
        client,
        vacancy,
        starts_at=starts_at + timedelta(minutes=30),
        ends_at=starts_at + timedelta(minutes=90),
    )
    assert overlapping.status_code == 409
    assert overlapping.json()["error"]["code"] == "slot_overlaps"
    assert overlapping.json()["error"]["details"]["slot_id"] == first.json()["id"]
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 1

    # 2. Пересечение проверяется по работодателю, а не по вакансии: он не
    # может вести два собеседования одновременно даже на разных вакансиях
    other_vacancy = await _vacancy(employer)
    cross_vacancy = await _create_slot(
        client, other_vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert cross_vacancy.status_code == 409
    assert cross_vacancy.json()["error"]["code"] == "slot_overlaps"

    # 3. Слоты другого работодателя не мешают, даже если время совпадает
    isolated_vacancy = await _vacancy(employer)
    isolated_starts_at = _at(days=10)
    other_employer = await _other_employer()
    other_employer_vacancy = await _vacancy(other_employer)
    await _slot(other_employer_vacancy, other_employer, starts_at=isolated_starts_at)
    not_blocked = await _create_slot(
        client,
        isolated_vacancy,
        starts_at=isolated_starts_at,
        ends_at=isolated_starts_at + timedelta(hours=1),
    )
    assert not_blocked.status_code == 201, not_blocked.text

    # 4. Слот, начинающийся ровно в момент окончания предыдущего, не пересекается
    adjacent = await _create_slot(
        client,
        vacancy,
        starts_at=starts_at + timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=2),
    )
    assert adjacent.status_code == 201, adjacent.text
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 2

    # 5. Отменённый слот не блокирует создание нового на то же время
    cancelled_vacancy = await _vacancy(employer)
    cancelled_starts_at = _at(days=3)
    await _slot(
        cancelled_vacancy,
        employer,
        starts_at=cancelled_starts_at,
        status=InterviewSlotStatus.CANCELLED,
    )
    after_cancelled = await _create_slot(
        client,
        cancelled_vacancy,
        starts_at=cancelled_starts_at,
        ends_at=cancelled_starts_at + timedelta(hours=1),
    )
    assert after_cancelled.status_code == 201, after_cancelled.text


async def test_concurrent_overlapping_slots_produce_one(client: AsyncClient) -> None:
    """Проверка пересечения и вставка идут под одной блокировкой."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    starts_at = _at(days=1)

    responses = await asyncio.gather(
        *[
            _create_slot(
                client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
            )
            for _ in range(4)
        ]
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409, 409, 409]
    assert await InterviewSlot.filter(vacancy_id=vacancy.id).count() == 1


# --- Чтение слотов -------------------------------------------------------------


async def test_slot_listing(client: AsyncClient) -> None:
    # 1. Работодатель видит свои слоты, включая забронированные, но не отменённые
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    later = await _slot(vacancy, employer, starts_at=_at(days=2))
    earlier = await _slot(
        vacancy, employer, starts_at=_at(days=1), status=InterviewSlotStatus.BOOKED
    )
    await _slot(
        vacancy, employer, starts_at=_at(days=3), status=InterviewSlotStatus.CANCELLED
    )
    own_view = (await _list_slots(client, vacancy)).json()
    assert [item["id"] for item in own_view["items"]] == [earlier.id, later.id]
    assert own_view["items"][0]["status"] == InterviewSlotStatus.BOOKED.value
    assert own_view["match_id"] is None

    # 2. Чужие слоты работодателю не видны
    other = await _other_employer()
    foreign_vacancy = await _vacancy(other)
    await _slot(foreign_vacancy, other)
    foreign = await _list_slots(client, foreign_vacancy)
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "vacancy_not_found"

    # 3. Кандидату без взаимного интереса слоты не видны
    no_match_vacancy = await _vacancy(other)
    await _slot(no_match_vacancy, other)
    no_match_candidate = await _candidate()
    await _application(
        no_match_vacancy, no_match_candidate, status=ApplicationStatus.PASSED
    )
    await _login(client, no_match_candidate.user_id, UserRole.CANDIDATE)
    no_match = await _list_slots(client, no_match_vacancy)
    assert no_match.status_code == 403
    assert no_match.json()["error"]["code"] == "match_required"

    # 4. Кандидату со взаимным интересом видны только свободные будущие слоты
    matched_vacancy = await _vacancy(other)
    free = await _slot(matched_vacancy, other, starts_at=_at(days=1))
    await _slot(
        matched_vacancy, other, starts_at=_at(days=2), status=InterviewSlotStatus.BOOKED
    )
    await _slot(
        matched_vacancy,
        other,
        starts_at=_at(days=3),
        status=InterviewSlotStatus.CANCELLED,
    )
    await _slot(matched_vacancy, other, starts_at=utcnow() - timedelta(hours=1))
    match, _, candidate = await _matched(matched_vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    body = (await _list_slots(client, matched_vacancy)).json()
    assert [item["id"] for item in body["items"]] == [free.id]
    assert body["match_id"] == match.id
    assert body["interviews"] == []

    # 5. Просмотр слотов кандидатом логируется аналитикой (раздел 60)
    event = await AnalyticsEvent.filter(
        user_id=candidate.user_id, event_name="slot_viewed"
    ).get()
    assert event.payload == {
        "vacancy_id": matched_vacancy.id,
        "match_id": match.id,
        "slots": 1,
    }

    # 6. Несуществующая вакансия и не выбранная роль — тоже ошибки
    unknown = await client.get("/api/vacancies/999999/slots")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "vacancy_not_found"

    roleless_id = next(_candidate_ids)
    await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=roleless_id))},
    )
    no_role = await _list_slots(client, matched_vacancy)
    assert no_role.status_code == 403
    assert no_role.json()["error"]["code"] == "role_not_selected"


# --- Отмена слота ---------------------------------------------------------------


async def test_slot_cancellation(client: AsyncClient) -> None:
    # 1. Отмена скрывает слот из списка
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    cancelled = await _cancel_slot(client, vacancy, slot.id)
    assert cancelled.status_code == 204
    await slot.refresh_from_db()
    assert slot.status is InterviewSlotStatus.CANCELLED
    assert (await _list_slots(client, vacancy)).json()["items"] == []

    # 2. Повторная отмена — не ошибка
    already_cancelled = await _slot(
        vacancy, employer, status=InterviewSlotStatus.CANCELLED
    )
    assert (
        await _cancel_slot(client, vacancy, already_cancelled.id)
    ).status_code == 204

    # 3. Забронированный слот отменить нельзя
    booked = await _slot(vacancy, employer, status=InterviewSlotStatus.BOOKED)
    booked_response = await _cancel_slot(client, vacancy, booked.id)
    assert booked_response.status_code == 409
    assert booked_response.json()["error"]["code"] == "slot_booked"
    await booked.refresh_from_db()
    assert booked.status is InterviewSlotStatus.BOOKED

    # 4. Чужой слот нельзя отменить ни через свою, ни через чужую вакансию
    other = await _other_employer()
    foreign_vacancy = await _vacancy(other)
    foreign_slot = await _slot(foreign_vacancy, other)
    by_own_vacancy = await _cancel_slot(client, vacancy, foreign_slot.id)
    by_foreign_vacancy = await _cancel_slot(client, foreign_vacancy, foreign_slot.id)
    assert by_own_vacancy.status_code == 404
    assert by_own_vacancy.json()["error"]["code"] == "slot_not_found"
    assert by_foreign_vacancy.status_code == 404
    assert by_foreign_vacancy.json()["error"]["code"] == "vacancy_not_found"
    await foreign_slot.refresh_from_db()
    assert foreign_slot.status is InterviewSlotStatus.AVAILABLE

    # 5. Кандидату отмена недоступна вовсе
    candidate_target = await _slot(vacancy, employer)
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    candidate_response = await _cancel_slot(client, vacancy, candidate_target.id)
    assert candidate_response.status_code == 403
    assert candidate_response.json()["error"]["code"] == "wrong_role"


# --- Бронирование: happy path и идемпотентность ---------------------------------


async def test_booking_happy_path_and_idempotency(client: AsyncClient) -> None:
    # 1. Бронирование создаёт собеседование и переводит отклик (раздел 56)
    employer = await _other_employer()
    vacancy = await _vacancy(employer)
    slot = await _slot(vacancy, employer)
    match, application, candidate = await _matched(vacancy)
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    booked = await _book(client, match, slot.id)
    assert booked.status_code == 201, booked.text
    body = booked.json()
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

    # 2. Повтор запроса не создаёт второе собеседование (раздел 79)
    repeated = await _book(client, match, slot.id)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == body["id"]
    assert await Interview.filter(match_id=match.id).count() == 1

    # 3. Перенос собеседования на другой слот — P1, сейчас отклонён
    other_slot = await _slot(vacancy, employer, starts_at=_at(days=5))
    reschedule = await _book(client, match, other_slot.id)
    assert reschedule.status_code == 409
    assert reschedule.json()["error"]["code"] == "interview_already_scheduled"
    await other_slot.refresh_from_db()
    assert other_slot.status is InterviewSlotStatus.AVAILABLE

    # 4. Занятый слот нельзя забронировать второй раз, даже другим кандидатом
    # (раздел 57: занятый слот — 409 Conflict)
    second_match, second_application, second_candidate = await _matched(vacancy)
    await _login(client, second_candidate.user_id, UserRole.CANDIDATE)
    taken = await _book(client, second_match, slot.id)
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slot_taken"
    assert await Interview.filter(slot_id=slot.id).count() == 1
    await second_application.refresh_from_db()
    assert second_application.status is ApplicationStatus.MUTUAL_INTEREST

    # 5. Аналитика фиксирует бронирование (раздел 60)
    event = await AnalyticsEvent.filter(
        user_id=candidate.user_id, event_name="interview_booked"
    ).get()
    assert event.payload == {
        "interview_id": body["id"],
        "match_id": match.id,
        "application_id": application.id,
        "vacancy_id": vacancy.id,
        "slot_id": slot.id,
    }

    # 6. После перезахода экран «Интервью назначено» восстанавливается из
    # состояния на сервере: занятый слот больше не предлагается
    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    reload_view = (await _list_slots(client, vacancy)).json()
    assert [item["id"] for item in reload_view["items"]] == [other_slot.id]
    assert len(reload_view["interviews"]) == 1
    reloaded_interview = reload_view["interviews"][0]
    assert reloaded_interview["slot"]["id"] == slot.id
    assert reloaded_interview["status"] == InterviewStatus.SCHEDULED.value
    assert (
        reloaded_interview["application_status"]
        == ApplicationStatus.INTERVIEW_SCHEDULED.value
    )


# --- Бронирование: guard'ы и предусловия -----------------------------------------


async def test_booking_guards_and_preconditions(client: AsyncClient) -> None:
    # 1. Отменённый и прошедший слот забронировать нельзя
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

    # 2. Слот другой вакансии того же работодателя забронировать нельзя
    other_vacancy = await _vacancy(employer)
    foreign_slot = await _slot(other_vacancy, employer)
    wrong_vacancy = await _book(client, match, foreign_slot.id)
    assert wrong_vacancy.status_code == 404
    assert wrong_vacancy.json()["error"]["code"] == "slot_not_found"

    # 3. Несуществующий слот и несуществующий match — 404
    unknown_slot = await _book(client, match, 999999)
    assert unknown_slot.status_code == 404
    assert unknown_slot.json()["error"]["code"] == "slot_not_found"

    unknown_match = await client.post(
        "/api/matches/999999/book", json={"slot_id": 1}
    )
    assert unknown_match.status_code == 404
    assert unknown_match.json()["error"]["code"] == "match_not_found"

    # 4. Чужой match забронировать нельзя, статус отклика не меняется
    foreign_match, foreign_application, _ = await _matched(vacancy)
    foreign_slot_for_match = await _slot(vacancy, employer, starts_at=_at(days=2))
    await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    foreign_match_response = await _book(
        client, foreign_match, foreign_slot_for_match.id
    )
    assert foreign_match_response.status_code == 404
    assert foreign_match_response.json()["error"]["code"] == "match_not_found"
    await foreign_application.refresh_from_db()
    assert foreign_application.status is ApplicationStatus.MUTUAL_INTEREST

    # 5. Работодателю бронирование недоступно, без сессии — тоже
    role_vacancy_owner = await _employer(client)
    role_vacancy = await _vacancy(role_vacancy_owner)
    role_slot = await _slot(role_vacancy, role_vacancy_owner)
    role_match, _, _ = await _matched(role_vacancy)
    wrong_role = await _book(client, role_match, role_slot.id)
    assert wrong_role.status_code == 403
    assert wrong_role.json()["error"]["code"] == "wrong_role"

    async with _fresh_client() as guest:
        session_vacancy_owner = await _other_employer()
        session_vacancy = await _vacancy(session_vacancy_owner)
        session_slot = await _slot(session_vacancy, session_vacancy_owner)
        session_match, _, _ = await _matched(session_vacancy)
        assert (
            await _book(guest, session_match, session_slot.id)
        ).status_code == 401

    # 6. До взаимного интереса бронирование отклоняется картой переходов
    # раздела 26
    early_owner = await _other_employer()
    early_vacancy = await _vacancy(early_owner)
    early_slot = await _slot(early_vacancy, early_owner)
    early_candidate = await _candidate()
    early_application = await _application(
        early_vacancy, early_candidate, status=ApplicationStatus.PASSED
    )
    early_match = await Match.create(application_id=early_application.id)
    await _login(client, early_candidate.user_id, UserRole.CANDIDATE)
    too_early = await _book(client, early_match, early_slot.id)
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "invalid_state_transition"
    await early_slot.refresh_from_db()
    assert early_slot.status is InterviewSlotStatus.AVAILABLE


# --- Конкурентность и гонки (диагностика важнее компактности) -------------------


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


# --- Сквозной путь этапа: приглашение → назначенное собеседование ---------------


async def test_end_to_end_interview_scheduling(client: AsyncClient) -> None:
    """Приглашение → взаимный интерес → слот → бронирование → назначено.

    Результат обязательного маршрута P0 (раздел 1): `Interview scheduled`.
    """
    # 1. Приглашение → слот → бронирование → назначенное собеседование
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
    slot_response = await _create_slot(
        client, vacancy, starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)
    )
    assert slot_response.status_code == 201, slot_response.text
    slot_id = slot_response.json()["id"]
    other_slot_response = await _create_slot(
        client, vacancy, starts_at=_at(days=2), ends_at=_at(days=2, hours=1)
    )
    assert other_slot_response.status_code == 201, other_slot_response.text

    await _login(client, candidate.user_id, UserRole.CANDIDATE)
    available = (await _list_slots(client, vacancy)).json()
    assert slot_id in [item["id"] for item in available["items"]]
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

    # 2. Работодателю видно не только «слот занят», но и с кем встреча —
    # без раскрытия личных данных кандидата (раздел 34)
    await _login(client, employer.user_id, UserRole.EMPLOYER)
    employer_view = (await _list_slots(client, vacancy)).json()
    scheduled = next(
        item for item in employer_view["interviews"] if item["slot"]["id"] == slot_id
    )
    assert scheduled["application_id"] == application.id
    assert scheduled["match_id"] == match_id
    assert scheduled["status"] == InterviewStatus.SCHEDULED.value
    assert "Кандидат" not in str(employer_view)

    # 3. Другой кандидат по той же вакансии это собеседование не видит
    other_match, other_application, other_candidate = await _matched(vacancy)
    await _login(client, other_candidate.user_id, UserRole.CANDIDATE)
    other_view = (await _list_slots(client, vacancy)).json()
    assert other_view["match_id"] == other_match.id
    assert other_view["interviews"] == []
    assert str(other_application.id) not in str(other_view["interviews"])
