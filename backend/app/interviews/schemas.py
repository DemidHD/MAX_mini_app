"""Схемы слотов и собеседований. Разделы 22, 23, 27, 37, 52 тех-доки."""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel

from app.core.enums import ApplicationStatus, InterviewSlotStatus, InterviewStatus


class SlotCreateRequest(BaseModel):
    """Один слот работодателя (раздел 37).

    Время принимается только со смещением (`2026-10-01T10:00:00Z` или
    `+03:00`): без него непонятно, в каком часовом поясе назначено
    собеседование, а ошибиться здесь — значит не встретиться.

    `employer_id` в теле не принимается: работодатель определяется сессией.
    """

    starts_at: AwareDatetime
    ends_at: AwareDatetime


class InterviewSlotRead(BaseModel):
    """Слот в ответе API."""

    id: int
    vacancy_id: int
    starts_at: datetime
    ends_at: datetime
    status: InterviewSlotStatus


class InterviewRead(BaseModel):
    """Назначенное собеседование. Раздел 23 тех-доки.

    `application_status` повторяет статус отклика после бронирования: экран
    «Интервью назначено» показывает и время, и состояние отклика, а отдельного
    эндпоинта отклика в разделе 27 нет.
    """

    id: int
    match_id: int
    application_id: int
    vacancy_id: int
    slot: InterviewSlotRead
    status: InterviewStatus
    application_status: ApplicationStatus
    created_at: datetime


class SlotListResponse(BaseModel):
    """Слоты вакансии.

    Состав ответа зависит от того, кто спрашивает: работодатель видит все
    свои действующие слоты, кандидат — только свободные и только будущие.

    `match_id` заполняется только кандидату: с ним он идёт бронировать.

    `interviews` — уже назначенные собеседования: у кандидата это его
    собственное (ноль или одно), у работодателя — все по этой вакансии.
    Занятый слот в `items` кандидату не попадает, поэтому показать время
    назначенного собеседования можно только отсюда.
    """

    vacancy_id: int
    items: list[InterviewSlotRead]
    match_id: int | None
    interviews: list[InterviewRead]


class BookingRequest(BaseModel):
    """Выбор времени кандидатом. Раздел 37 тех-доки."""

    slot_id: int
