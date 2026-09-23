"""Слоты собеседований и бронирование. Разделы 22, 23, 26, 37, 56, 57 тех-доки.

Порядок бронирования задан разделом 56 и здесь не сокращается:

```text
lock slot → verify available → book slot → create interview → update application
```

Всё это одна транзакция: занятый слот должен приводить к `409` (раздел 57),
а не ко второму собеседованию на то же время. Уведомления (раздел 46)
отправляются после commit и подключаются на этапе 7 — ошибка уведомления
созданное собеседование не отменяет (раздел 47).
"""

import logging
from datetime import datetime, timedelta, timezone

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import Application, Match
from app.applications.state import ensure_transition
from app.core.config import settings
from app.core.database import utcnow
from app.core.enums import (
    ApplicationStatus,
    InterviewSlotStatus,
    InterviewStatus,
    UserRole,
)
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.interviews.models import Interview, InterviewSlot
from app.interviews.schemas import (
    BookingRequest,
    InterviewRead,
    InterviewSlotRead,
    SlotCreateRequest,
    SlotListResponse,
)
from app.notifications.service import SlotRecipient, notification_service
from app.users.models import User
from app.vacancies import service as vacancies_service
from app.vacancies.models import Vacancy

logger = logging.getLogger("app.interviews")

# Отменённый слот остаётся в БД, но нигде не показывается: это след решения
# работодателя, а не доступное время.
ACTIVE_SLOT_STATUSES = (InterviewSlotStatus.AVAILABLE, InterviewSlotStatus.BOOKED)


async def create_slot(
    user: User, vacancy_id: int, payload: SlotCreateRequest
) -> InterviewSlotRead:
    """Работодатель добавляет время для собеседования (раздел 37).

    Один запрос — один слот: пакетное создание тех-дока не описывает, а
    частичный успех пачки пришлось бы как-то показывать в интерфейсе.

    Пересечения проверяются по всем вакансиям работодателя: человек не может
    проводить два собеседования одновременно, даже если вакансии разные.
    Проверка и вставка идут под блокировкой самого работодателя — иначе два
    параллельных запроса оба прошли бы проверку.

    Кандидатам со взаимным интересом уходит `interview_slot_available`
    (раздел 46) — после commit, ошибка отправки слот не отменяет.
    """
    vacancy = await vacancies_service.get_own_vacancy(user, vacancy_id)
    starts_at, ends_at = _validated_interval(payload)

    async with in_transaction() as connection:
        await (
            User.filter(user_id=user.user_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        overlapping = await (
            InterviewSlot.filter(
                employer_id=user.user_id,
                status__in=ACTIVE_SLOT_STATUSES,
                starts_at__lt=ends_at,
                ends_at__gt=starts_at,
            )
            .using_db(connection)
            .first()
        )
        if overlapping is not None:
            raise ConflictError(
                "Слот пересекается с уже созданным",
                code="slot_overlaps",
                details={
                    "slot_id": overlapping.id,
                    "vacancy_id": overlapping.vacancy_id,
                },
            )

        slot = await InterviewSlot.create(
            employer_id=user.user_id,
            vacancy_id=vacancy.id,
            starts_at=starts_at,
            ends_at=ends_at,
            status=InterviewSlotStatus.AVAILABLE,
            using_db=connection,
        )

    await _notify_slot_available(slot, vacancy)
    logger.info("Создан слот %s по вакансии %s", slot.id, vacancy.id)
    return _slot_read(slot)


async def list_slots(user: User, vacancy_id: int) -> SlotListResponse:
    """Слоты вакансии для того, кто их спрашивает (раздел 37).

    Работодатель видит все свои действующие слоты, включая занятые: ему нужна
    своя занятость целиком. Кандидат видит только то, что реально можно
    выбрать, — свободные и ещё не прошедшие слоты, и только при взаимном
    интересе по этой вакансии.
    """
    if user.role is UserRole.EMPLOYER:
        return await _employer_slots(user, vacancy_id)
    if user.role is UserRole.CANDIDATE:
        return await _candidate_slots(user, vacancy_id)
    # До выбора роли доступны только onboarding-эндпоинты (раздел 12)
    raise ForbiddenError("Сначала нужно выбрать роль", code="role_not_selected")


async def cancel_slot(user: User, vacancy_id: int, slot_id: int) -> None:
    """Работодатель снимает своё время.

    Отдельного эндпоинта отмены в тех-доке нет: раздел 37 описывает создание,
    чтение и бронирование. Слот не удаляется, а переводится в `cancelled` —
    на него могла ссылаться история, а `interviews.slot_id` защищён
    `RESTRICT`.

    Занятый слот не отменяется: за ним стоит назначенное собеседование, а
    отмена собеседования (`interview_cancelled`, раздел 46) относится к P1.
    Повторная отмена ничего не меняет и ошибкой не считается.
    """
    vacancy = await vacancies_service.get_own_vacancy(user, vacancy_id)

    async with in_transaction() as connection:
        locked = await (
            InterviewSlot.filter(id=slot_id, vacancy_id=vacancy.id)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if locked is None:
            raise NotFoundError("Слот не найден", code="slot_not_found")
        if locked.status is InterviewSlotStatus.CANCELLED:
            return
        if locked.status is InterviewSlotStatus.BOOKED:
            raise ConflictError(
                "Слот забронирован: отмена собеседования относится к P1",
                code="slot_booked",
                details={"slot_id": locked.id},
            )

        locked.status = InterviewSlotStatus.CANCELLED
        await locked.save(using_db=connection, update_fields=["status"])

    logger.info("Отменён слот %s по вакансии %s", slot_id, vacancy.id)


async def book(
    user: User, match_id: int, payload: BookingRequest
) -> tuple[InterviewRead, bool]:
    """Кандидат бронирует слот (разделы 37, 56).

    Возвращает собеседование и признак того, что оно создано именно этим
    запросом: повтор того же запроса собеседование не дублирует (раздел 79),
    а возвращает уже назначенное.
    """
    match, application = await _own_match(user, match_id)

    async with in_transaction() as connection:
        # Отклик блокируется первым и всегда первым: тот же порядок блокировок
        # в решении работодателя, поэтому взаимной блокировки не возникает
        locked_application = await (
            Application.filter(id=application.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        existing = await (
            Interview.filter(match_id=match.id).using_db(connection).first()
        )
        if existing is not None:
            return (
                await _existing_interview(
                    existing, locked_application, payload.slot_id, connection
                ),
                False,
            )

        ensure_transition(
            locked_application.status, ApplicationStatus.INTERVIEW_SCHEDULED
        )

        # Раздел 56: слот блокируется до проверки доступности, иначе два
        # кандидата успеют прочитать его свободным
        locked_slot = await (
            InterviewSlot.filter(
                id=payload.slot_id, vacancy_id=locked_application.vacancy_id
            )
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if locked_slot is None:
            raise NotFoundError("Слот не найден", code="slot_not_found")
        _ensure_bookable(locked_slot)

        interview = await Interview.create(
            match_id=match.id,
            slot_id=locked_slot.id,
            status=InterviewStatus.SCHEDULED,
            using_db=connection,
        )
        locked_slot.status = InterviewSlotStatus.BOOKED
        await locked_slot.save(using_db=connection, update_fields=["status"])

        locked_application.status = ApplicationStatus.INTERVIEW_SCHEDULED
        await locked_application.save(
            using_db=connection, update_fields=["status", "updated_at"]
        )

    await analytics.log_event(
        "interview_booked",
        user_id=user.user_id,
        payload={
            "interview_id": interview.id,
            "match_id": match.id,
            "application_id": locked_application.id,
            "vacancy_id": locked_application.vacancy_id,
            "slot_id": locked_slot.id,
        },
    )
    await _notify_interview_booked(interview, locked_slot, locked_application)
    logger.info(
        "Назначено собеседование %s: match=%s слот=%s",
        interview.id,
        match.id,
        locked_slot.id,
    )
    return _interview_read(interview, locked_slot, locked_application, match.id), True


async def _notify_slot_available(slot: InterviewSlot, vacancy: Vacancy) -> None:
    """Сообщает о новом времени тем, кто его ждёт (раздел 46).

    Получатели — кандидаты со взаимным интересом по этой вакансии, которые
    ещё не выбрали время: у кого собеседование уже назначено, тому новое
    время не нужно, а остальным отклик его и не показывает.

    Сообщение приходит один раз на вакансию: сущность события — вакансия,
    а не слот, иначе пять слотов подряд дали бы пять уведомлений.
    """
    waiting = await Application.filter(
        vacancy_id=vacancy.id, status=ApplicationStatus.MUTUAL_INTEREST
    )
    if not waiting:
        return

    await notification_service.interview_slot_available(
        vacancy_id=vacancy.id,
        vacancy_title=vacancy.title,
        recipients=[
            SlotRecipient(
                user_id=application.candidate_id, application_id=application.id
            )
            for application in waiting
        ],
    )


async def _notify_interview_booked(
    interview: Interview, slot: InterviewSlot, application: Application
) -> None:
    """Сообщает обеим сторонам, что собеседование назначено (раздел 47)."""
    vacancy = await Vacancy.get_or_none(id=application.vacancy_id)
    if vacancy is None:
        # FK с каскадом: отклика без вакансии не бывает
        logger.warning("Вакансия отклика %s не найдена", application.id)
        return

    await notification_service.interview_booked(
        interview_id=interview.id,
        application_id=application.id,
        candidate_id=application.candidate_id,
        employer_id=slot.employer_id,
        vacancy_title=vacancy.title,
        starts_at=slot.starts_at,
    )


async def _employer_slots(user: User, vacancy_id: int) -> SlotListResponse:
    vacancy = await vacancies_service.get_own_vacancy(user, vacancy_id)
    slots = await InterviewSlot.filter(
        vacancy_id=vacancy.id, status__in=ACTIVE_SLOT_STATUSES
    ).order_by("starts_at", "id")

    return SlotListResponse(
        vacancy_id=vacancy.id,
        items=[_slot_read(slot) for slot in slots],
        match_id=None,
        interviews=await _vacancy_interviews(slots),
    )


async def _vacancy_interviews(slots: list[InterviewSlot]) -> list[InterviewRead]:
    """Назначенные собеседования по слотам вакансии — для работодателя.

    Без этого работодатель видел бы только, что слот занят, но не знал бы,
    с каким откликом встречается. Личных данных здесь нет: экран решения
    работает с откликом, а не с именем (раздел 34).
    """
    booked = [slot for slot in slots if slot.status is InterviewSlotStatus.BOOKED]
    if not booked:
        return []

    slots_by_id = {slot.id: slot for slot in booked}
    interviews = await Interview.filter(slot_id__in=list(slots_by_id))
    if not interviews:
        return []

    matches = {
        match.id: match
        for match in await Match.filter(
            id__in=[interview.match_id for interview in interviews]
        )
    }
    applications = {
        application.id: application
        for application in await Application.filter(
            id__in=[match.application_id for match in matches.values()]
        )
    }

    result: list[InterviewRead] = []
    for interview in interviews:
        match = matches.get(interview.match_id)
        application = None if match is None else applications.get(match.application_id)
        if application is None:
            # FK с каскадом: собеседования без отклика не бывает
            logger.warning("У собеседования %s нет отклика", interview.id)
            continue
        result.append(
            _interview_read(
                interview,
                slots_by_id[interview.slot_id],
                application,
                interview.match_id,
            )
        )
    result.sort(key=lambda item: item.slot.starts_at)
    return result


async def _candidate_slots(user: User, vacancy_id: int) -> SlotListResponse:
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")

    application = await Application.get_or_none(
        vacancy_id=vacancy.id, candidate_id=user.user_id
    )
    match = (
        None
        if application is None
        else await Match.get_or_none(application_id=application.id)
    )
    if application is None or match is None:
        # Время работодателя видно только после взаимного интереса
        raise ForbiddenError(
            "Слоты доступны после взаимного интереса",
            code="match_required",
            details={"vacancy_id": vacancy.id},
        )

    slots = await InterviewSlot.filter(
        vacancy_id=vacancy.id,
        status=InterviewSlotStatus.AVAILABLE,
        starts_at__gt=utcnow(),
    ).order_by("starts_at", "id")

    interview = await Interview.get_or_none(match_id=match.id)
    interviews: list[InterviewRead] = []
    if interview is not None:
        booked_slot = await InterviewSlot.get(id=interview.slot_id)
        interviews.append(
            _interview_read(interview, booked_slot, application, match.id)
        )

    await analytics.log_event(
        "slot_viewed",
        user_id=user.user_id,
        payload={
            "vacancy_id": vacancy.id,
            "match_id": match.id,
            "slots": len(slots),
        },
    )

    return SlotListResponse(
        vacancy_id=vacancy.id,
        items=[_slot_read(slot) for slot in slots],
        match_id=match.id,
        interviews=interviews,
    )


async def _own_match(user: User, match_id: int) -> tuple[Match, Application]:
    """Взаимный интерес текущего кандидата и отклик, к которому он относится.

    Чужой match — `404`: наружу не раскрывается даже его существование.
    """
    match = await Match.get_or_none(id=match_id)
    application = (
        None
        if match is None
        else await Application.get_or_none(id=match.application_id)
    )
    if match is None or application is None:
        raise NotFoundError("Взаимный интерес не найден", code="match_not_found")
    if application.candidate_id != user.user_id:
        raise NotFoundError("Взаимный интерес не найден", code="match_not_found")
    return match, application


async def _existing_interview(
    interview: Interview,
    application: Application,
    requested_slot_id: int,
    connection: BaseDBAsyncClient,
) -> InterviewRead:
    """Ответ на повторное бронирование.

    Тот же слот — возвращается уже назначенное собеседование (раздел 79).
    Другой слот — это перенос, а `interview_rescheduled` относится к P1
    (раздел 46), поэтому `409`.
    """
    if interview.slot_id != requested_slot_id:
        raise ConflictError(
            "Собеседование уже назначено на другое время",
            code="interview_already_scheduled",
            details={"interview_id": interview.id, "slot_id": interview.slot_id},
        )

    slot = await InterviewSlot.filter(id=interview.slot_id).using_db(connection).get()
    return _interview_read(interview, slot, application, interview.match_id)


def _ensure_bookable(slot: InterviewSlot) -> None:
    """Раздел 57: занятый слот — `409 Conflict`."""
    if slot.status is InterviewSlotStatus.BOOKED:
        raise ConflictError(
            "Слот уже занят", code="slot_taken", details={"slot_id": slot.id}
        )
    if slot.status is InterviewSlotStatus.CANCELLED:
        raise ConflictError(
            "Слот отменён работодателем",
            code="slot_cancelled",
            details={"slot_id": slot.id},
        )
    if slot.starts_at <= utcnow():
        raise ConflictError(
            "Время слота уже прошло",
            code="slot_in_past",
            details={"slot_id": slot.id},
        )


def _validated_interval(payload: SlotCreateRequest) -> tuple[datetime, datetime]:
    """Проверяет интервал слота и приводит его к UTC.

    Смещение уже гарантировано схемой; здесь проверяется то, что зависит от
    текущего времени и настроек.
    """
    starts_at = payload.starts_at.astimezone(timezone.utc)
    ends_at = payload.ends_at.astimezone(timezone.utc)

    if ends_at <= starts_at:
        raise ValidationError(
            "Слот должен заканчиваться позже, чем начинается",
            code="slot_interval_invalid",
        )
    if starts_at <= utcnow():
        raise ValidationError("Слот должен начинаться в будущем", code="slot_in_past")

    duration = ends_at - starts_at
    minimum = timedelta(minutes=settings.interview_slot_min_duration_minutes)
    maximum = timedelta(hours=settings.interview_slot_max_duration_hours)
    if duration < minimum:
        raise ValidationError(
            "Слот слишком короткий",
            code="slot_too_short",
            details={"min_minutes": settings.interview_slot_min_duration_minutes},
        )
    if duration > maximum:
        raise ValidationError(
            "Слот слишком длинный",
            code="slot_too_long",
            details={"max_hours": settings.interview_slot_max_duration_hours},
        )
    return starts_at, ends_at


def _slot_read(slot: InterviewSlot) -> InterviewSlotRead:
    return InterviewSlotRead(
        id=slot.id,
        vacancy_id=slot.vacancy_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        status=slot.status,
    )


def _interview_read(
    interview: Interview,
    slot: InterviewSlot,
    application: Application,
    match_id: int,
) -> InterviewRead:
    return InterviewRead(
        id=interview.id,
        match_id=match_id,
        application_id=application.id,
        vacancy_id=application.vacancy_id,
        slot=_slot_read(slot),
        status=interview.status,
        application_status=application.status,
        created_at=interview.created_at,
    )
