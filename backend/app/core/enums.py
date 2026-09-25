"""Перечисления бизнес-состояний. Значения соответствуют тех-доке и хранятся в БД как строки."""

from enum import StrEnum


class UserRole(StrEnum):
    """Раздел 8. NULL (роль не выбрана) выражается отсутствием значения в колонке."""

    CANDIDATE = "candidate"
    EMPLOYER = "employer"


class VacancyStatus(StrEnum):
    """Раздел 15."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class CriterionType(StrEnum):
    """Раздел 16."""

    LOCATION = "location"
    SCHEDULE = "schedule"
    SALARY = "salary"
    AVAILABLE_FROM = "available_from"
    EXPERIENCE = "experience"
    CERTIFICATE = "certificate"


class ScreeningQuestionType(StrEnum):
    """Раздел 18: тип ожидаемого ответа."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"


class ApplicationStatus(StrEnum):
    """Раздел 17.

    `reserved` — функция «Резерв» (P1, раздел 20): промежуточное состояние
    между первичным отбором и финальным решением, из которого работодатель
    может позже пригласить или отклонить кандидата.
    """

    CREATED = "created"
    SCREENING = "screening"
    HARD_FILTER_FAILED = "hard_filter_failed"
    PASSED = "passed"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"
    RESERVED = "reserved"
    INVITED = "invited"
    MUTUAL_INTEREST = "mutual_interest"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_COMPLETED = "interview_completed"


class DecisionAction(StrEnum):
    """Раздел 20. `reserved` — функция «Резерв» (P1)."""

    REJECTED = "rejected"
    RESERVED = "reserved"
    INVITED = "invited"


class RejectReason(StrEnum):
    """Раздел 20."""

    EXPERIENCE = "experience"
    SALARY = "salary"
    SCHEDULE = "schedule"
    LOCATION = "location"
    AVAILABLE_FROM = "available_from"
    OTHER = "other"


class InterviewSlotStatus(StrEnum):
    """Раздел 22."""

    AVAILABLE = "available"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class InterviewStatus(StrEnum):
    """Раздел 23. Для P0 достаточно `scheduled`."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class NotificationType(StrEnum):
    """Раздел 46.

    Остальные типы раздела 46 (`interview_cancelled`, `interview_rescheduled`,
    `interview_reminder`, `application_status_changed`) в P2 не входят
    (функции 27-28 UX-карты требуют только отказ) и пока не заводятся.
    """

    APPLICATION_CREATED = "application_created"
    CANDIDATE_INVITED = "candidate_invited"
    MUTUAL_INTEREST = "mutual_interest"
    INTERVIEW_SLOT_AVAILABLE = "interview_slot_available"
    INTERVIEW_BOOKED = "interview_booked"
    # P1 — функция «Резерв» (раздел 20)
    APPLICATION_RESERVED = "application_reserved"
    # P2 — автосообщение об отказе (функции 27-28 UX-карты, раздел 46 тех-доки)
    APPLICATION_REJECTED = "application_rejected"


class NotificationStatus(StrEnum):
    """Состояние доставки уведомления. Раздел 48.

    `pending` — уведомление заведено, но не доставлено: отправка ещё не
    удалась либо канал отключён. Такое уведомление можно отправить повторно,
    `sent` — нельзя (раздел 50).
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
