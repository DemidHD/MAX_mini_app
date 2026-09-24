"""Уведомления в MAX. Разделы 44, 46-50, 47 тех-доки.

Проверяется и то, что уведомление уходит, и то, что его отсутствие или
ошибка не ломают бизнес-операцию. Все события одного happy path (отклик →
отказ/приглашение → слот → бронирование) собраны в один сквозной сценарий.
Тесты на надёжность доставки (retry, дубликаты, сбой транспорта) оставлены
отдельными: у каждого свой транспорт и своя точка отказа, сливать их в общий
поток — терять точную диагностику без выигрыша в количестве.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.analytics.models import AnalyticsEvent
from app.applications.models import Application, Match
from app.candidates.models import CandidateProfile
from app.core.config import settings
from app.core.database import utcnow
from app.core.enums import (
    ApplicationStatus,
    InterviewSlotStatus,
    NotificationStatus,
    NotificationType,
    UserRole,
    VacancyStatus,
)
from app.interviews.models import Interview, InterviewSlot
from app.notifications import messages
from app.notifications.models import NotificationLog
from app.notifications.service import notification_service
from app.notifications.transport import NotificationsDisabledError
from app.users.models import User
from app.vacancies.models import Vacancy
from tests.factories import build_init_data, max_user_payload
from tests.fakes import FailingTransport, RecordingTransport

_employer_ids = count(810000)
_candidate_ids = count(811000)

FITTING_PROFILE: dict[str, Any] = {
    "desired_role": "Бариста",
    "city": "Москва",
    "salary": Decimal("70000"),
    "schedule": "full_time",
    "experience_months": 24,
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_vacancies():
    yield
    vacancy_ids = await Vacancy.filter(
        employer_id__gte=810000, employer_id__lt=811000
    ).values_list("id", flat=True)
    if not vacancy_ids:
        return
    slot_ids = await InterviewSlot.filter(vacancy_id__in=vacancy_ids).values_list(
        "id", flat=True
    )
    if slot_ids:
        await Interview.filter(slot_id__in=slot_ids).delete()
    await Vacancy.filter(id__in=vacancy_ids).delete()


async def _login(client: AsyncClient, user_id: int, role: UserRole) -> User:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200, response.text
    await User.filter(user_id=user_id).update(role=role)
    return await User.get(user_id=user_id)


async def _employer(client: AsyncClient) -> User:
    return await _login(client, next(_employer_ids), UserRole.EMPLOYER)


async def _vacancy(employer: User, title: str = "Бариста в центре") -> Vacancy:
    return await Vacancy.create(
        employer=employer,
        title=title,
        location="Москва",
        salary_max=Decimal("90000"),
        schedule="full_time",
        status=VacancyStatus.PUBLISHED,
    )


async def _candidate(client: AsyncClient) -> User:
    candidate = await _login(client, next(_candidate_ids), UserRole.CANDIDATE)
    await CandidateProfile.create(user_id=candidate.user_id, **FITTING_PROFILE)
    return candidate


async def _passed_application(vacancy: Vacancy, candidate: User) -> Application:
    return await Application.create(
        vacancy=vacancy, candidate=candidate, status=ApplicationStatus.PASSED
    )


async def _matched(vacancy: Vacancy, candidate: User) -> Match:
    application = await Application.create(
        vacancy=vacancy, candidate=candidate, status=ApplicationStatus.MUTUAL_INTEREST
    )
    return await Match.create(application_id=application.id)


async def _slot(vacancy: Vacancy, employer: User, hours: int = 24) -> InterviewSlot:
    starts_at = utcnow() + timedelta(hours=hours)
    return await InterviewSlot.create(
        employer_id=employer.user_id,
        vacancy_id=vacancy.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        status=InterviewSlotStatus.AVAILABLE,
    )


# --- Сквозной поток событий: отклик → отказ/приглашение → слот → бронирование --


async def test_notification_events_flow(
    client: AsyncClient, notifications: RecordingTransport
) -> None:
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    # 1. Отклик уведомляет работодателя, но не самого кандидата
    applicant = await _candidate(client)
    created = await client.post(f"/api/vacancies/{vacancy.id}/apply")
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]
    apply_texts = notifications.texts_for(employer.user_id)
    assert len(apply_texts) == 1
    assert "Новый отклик" in apply_texts[0]
    assert vacancy.title in apply_texts[0]
    assert notifications.texts_for(applicant.user_id) == []
    application_log = await NotificationLog.get(
        event_type=NotificationType.APPLICATION_CREATED,
        entity_id=application_id,
        user_id=employer.user_id,
    )
    assert application_log.status is NotificationStatus.SENT
    assert application_log.attempts == 1

    # 2. То же событие доставки пишется в аналитику (раздел 60)
    delivery_event = await AnalyticsEvent.filter(
        user_id=employer.user_id, event_name="notification_sent"
    ).get()
    assert delivery_event.payload["event_type"] == (
        NotificationType.APPLICATION_CREATED.value
    )
    assert delivery_event.payload["entity_id"] == application_id
    notifications.clear()

    # 3. Отказ решением не уведомляет кандидата — P1/P2, раздел 46
    rejected_candidate = await _candidate(client)
    rejected_application = await _passed_application(vacancy, rejected_candidate)
    await _login(client, employer.user_id, UserRole.EMPLOYER)
    await client.post(
        f"/api/applications/{rejected_application.id}/decision",
        json={"action": "rejected"},
    )
    assert notifications.texts_for(rejected_candidate.user_id) == []
    notifications.clear()

    # 4. Приглашение уведомляет обе стороны: кандидата дважды, работодателя один раз
    invited_candidate = await _candidate(client)
    invited_application = await _passed_application(vacancy, invited_candidate)
    await _login(client, employer.user_id, UserRole.EMPLOYER)
    invited = await client.post(
        f"/api/applications/{invited_application.id}/decision",
        json={"action": "invited"},
    )
    assert invited.status_code == 200, invited.text
    candidate_texts = notifications.texts_for(invited_candidate.user_id)
    employer_texts = notifications.texts_for(employer.user_id)
    assert len(candidate_texts) == 2
    assert "пригласили" in candidate_texts[0]
    assert "Взаимный интерес" in candidate_texts[1]
    assert len(employer_texts) == 1
    assert "Взаимный интерес" in employer_texts[0]
    match_id = invited.json()["match_id"]
    assert await NotificationLog.filter(
        event_type=NotificationType.MUTUAL_INTEREST, entity_id=match_id
    ).count() == 2
    notifications.clear()

    # 5. Новый слот уведомляет только кандидатов со взаимным интересом
    uninterested = await _candidate(client)
    await _passed_application(vacancy, uninterested)
    await _login(client, employer.user_id, UserRole.EMPLOYER)
    starts_at = utcnow() + timedelta(days=1)
    first_slot = await client.post(
        f"/api/vacancies/{vacancy.id}/slots",
        json={
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        },
    )
    assert first_slot.status_code == 201, first_slot.text
    slot_texts = notifications.texts_for(invited_candidate.user_id)
    assert len(slot_texts) == 1
    assert "время собеседования" in slot_texts[0]
    assert notifications.texts_for(uninterested.user_id) == []

    # 6. Несколько слотов подряд не спамят кандидата повторными уведомлениями
    for day in (2, 3, 4):
        extra_starts_at = utcnow() + timedelta(days=day)
        extra_slot = await client.post(
            f"/api/vacancies/{vacancy.id}/slots",
            json={
                "starts_at": extra_starts_at.isoformat(),
                "ends_at": (extra_starts_at + timedelta(hours=1)).isoformat(),
            },
        )
        assert extra_slot.status_code == 201, extra_slot.text
    assert len(notifications.texts_for(invited_candidate.user_id)) == 1
    notifications.clear()

    # 7. Бронирование уведомляет обе стороны временем собеседования
    await _login(client, invited_candidate.user_id, UserRole.CANDIDATE)
    slot_id = first_slot.json()["id"]
    booked = await client.post(
        f"/api/matches/{match_id}/book", json={"slot_id": slot_id}
    )
    assert booked.status_code == 201, booked.text
    moment = messages.format_moment((await InterviewSlot.get(id=slot_id)).starts_at)
    booked_candidate_texts = notifications.texts_for(invited_candidate.user_id)
    booked_employer_texts = notifications.texts_for(employer.user_id)
    assert len(booked_candidate_texts) == 1 and moment in booked_candidate_texts[0]
    assert len(booked_employer_texts) == 1 and moment in booked_employer_texts[0]
    interview = await Interview.get(match_id=match_id)
    assert await NotificationLog.filter(
        event_type=NotificationType.INTERVIEW_BOOKED, entity_id=interview.id
    ).count() == 2


# --- Надёжность доставки (диагностика важнее компактности) --------------------


async def test_notification_failure_does_not_cancel_interview(
    client: AsyncClient, monkeypatch
) -> None:
    """Раздел 47: ошибка уведомления не откатывает созданное собеседование."""
    monkeypatch.setattr(settings, "notification_retry_delay_seconds", 0)
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    candidate = await _candidate(client)
    match = await _matched(vacancy, candidate)
    slot = await _slot(vacancy, employer)

    transport = FailingTransport()
    notification_service.set_transport(transport)
    booked = await client.post(
        f"/api/matches/{match.id}/book", json={"slot_id": slot.id}
    )

    assert booked.status_code == 201, booked.text
    interview = await Interview.get(match_id=match.id)
    assert interview.slot_id == slot.id
    application = await Application.get(id=match.application_id)
    assert application.status is ApplicationStatus.INTERVIEW_SCHEDULED

    log = await NotificationLog.get(
        event_type=NotificationType.INTERVIEW_BOOKED,
        entity_id=interview.id,
        user_id=candidate.user_id,
    )
    assert log.status is NotificationStatus.FAILED
    assert log.attempts == settings.notification_max_attempts
    assert "MAX недоступен" in log.error


async def test_temporary_error_is_retried(
    client: AsyncClient, notifications: RecordingTransport, monkeypatch
) -> None:
    """Раздел 49: временная ошибка приводит к повторной отправке."""
    monkeypatch.setattr(settings, "notification_retry_delay_seconds", 0)
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    await _candidate(client)
    notifications.fail_first = 1

    created = await client.post(f"/api/vacancies/{vacancy.id}/apply")

    assert created.status_code == 201, created.text
    assert notifications.attempts == 2
    assert len(notifications.texts_for(employer.user_id)) == 1
    log = await NotificationLog.get(
        event_type=NotificationType.APPLICATION_CREATED,
        entity_id=created.json()["id"],
        user_id=employer.user_id,
    )
    assert log.status is NotificationStatus.SENT
    assert log.attempts == 2


async def test_repeated_event_is_not_sent_twice(
    client: AsyncClient, notifications: RecordingTransport
) -> None:
    """Раздел 50: ключ `event_type + entity_id + user_id` уникален."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)

    for _ in range(3):
        await notification_service.application_created(
            employer_id=employer.user_id,
            application_id=4242,
            vacancy_title=vacancy.title,
        )

    assert len(notifications.texts_for(employer.user_id)) == 1
    assert (
        await NotificationLog.filter(
            event_type=NotificationType.APPLICATION_CREATED, entity_id=4242
        ).count()
        == 1
    )


async def test_failed_notification_can_be_sent_later(
    client: AsyncClient, notifications: RecordingTransport, monkeypatch
) -> None:
    """Неудачная отправка не блокирует повтор: `sent` блокирует, `failed` — нет."""
    monkeypatch.setattr(settings, "notification_retry_delay_seconds", 0)
    employer = await _employer(client)

    notification_service.set_transport(FailingTransport())
    await notification_service.application_created(
        employer_id=employer.user_id, application_id=4343, vacancy_title="Бариста"
    )
    notification_service.set_transport(notifications)
    await notification_service.application_created(
        employer_id=employer.user_id, application_id=4343, vacancy_title="Бариста"
    )

    assert len(notifications.texts_for(employer.user_id)) == 1
    log = await NotificationLog.get(
        event_type=NotificationType.APPLICATION_CREATED, entity_id=4343
    )
    assert log.status is NotificationStatus.SENT


async def test_disabled_channel_leaves_notification_pending(
    client: AsyncClient,
) -> None:
    """Выключенный канал — не отказ: уведомление остаётся неотправленным."""
    employer = await _employer(client)

    class _Disabled:
        async def send(
            self, user_id: int, text: str, *, deep_link: str | None = None
        ) -> None:
            raise NotificationsDisabledError("Уведомления выключены настройкой")

    notification_service.set_transport(_Disabled())
    await notification_service.application_created(
        employer_id=employer.user_id, application_id=4444, vacancy_title="Бариста"
    )

    log = await NotificationLog.get(
        event_type=NotificationType.APPLICATION_CREATED, entity_id=4444
    )
    assert log.status is NotificationStatus.PENDING
    assert log.attempts == 1


async def test_broken_notification_service_does_not_break_apply(
    client: AsyncClient,
) -> None:
    """Даже дефект самого сервиса уведомлений не должен ломать отклик."""
    employer = await _employer(client)
    vacancy = await _vacancy(employer)
    await _candidate(client)

    class _Broken:
        async def send(
            self, user_id: int, text: str, *, deep_link: str | None = None
        ) -> None:
            raise TypeError("дефект транспорта")

    notification_service.set_transport(_Broken())
    created = await client.post(f"/api/vacancies/{vacancy.id}/apply")

    assert created.status_code == 201, created.text
    assert await Application.filter(id=created.json()["id"]).exists()


# --- Тексты сообщений -----------------------------------------------------------


async def test_message_formatting(monkeypatch) -> None:
    # 1. Время хранится в UTC, а показывается в поясе пользователя продукта
    monkeypatch.setattr(settings, "notification_timezone", "Europe/Moscow")
    moment = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)
    assert messages.format_moment(moment) == "1 октября, 12:30 (МСК)"

    # 2. Неизвестный часовой пояс — откат на UTC
    monkeypatch.setattr(settings, "notification_timezone", "Mars/Olympus")
    assert messages.format_moment(moment) == "1 октября, 09:30 (UTC)"

    # 3. Путь для кнопки «Открыть детали» — маршрут Mini App, без APP_URL:
    # это start_param у OpenAppButton (maxapi), а не голая https-ссылка,
    # которая раньше открывалась в браузере без initData (баг демо)
    assert messages.employer_home_path() == "/employer"
    assert messages.application_path(7) == "/candidate/applications/7"
    assert messages.employer_application_path(7) == "/employer/applications/7"

    # 4. Текст уведомления больше не содержит саму ссылку — её несёт кнопка
    created = messages.application_created(vacancy_title="Бариста", application_id=7)
    assert "http" not in created.text
    assert created.path == "/employer/applications/7"
