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

    `reserved` относится к P1 и добавляется вместе с функцией «Резерв».
    """

    CREATED = "created"
    SCREENING = "screening"
    HARD_FILTER_FAILED = "hard_filter_failed"
    PASSED = "passed"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"
    INVITED = "invited"
    MUTUAL_INTEREST = "mutual_interest"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_COMPLETED = "interview_completed"


class DecisionAction(StrEnum):
    """Раздел 20.

    Колонка заводится сразу со всеми значениями, но в P0 backend принимает
    только `rejected` и `invited`; `reserved` до реализации P1 отклоняется как 422.
    """

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
