"""Pydantic-схемы профиля кандидата. Разделы 14, 27, 52 тех-доки.

Ограничения полей повторяют колонки `candidate_profiles`: значение, прошедшее
валидацию схемы, обязано записаться в БД без ошибки драйвера.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.candidates.models import CandidateProfile
from app.core.money import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    Money,
    quantize_money,
)

# Опыт хранится в INTEGER; 1200 месяцев — 100 лет, заведомо больше любой
# осмысленной карьеры и при этом отсекает мусорные значения
MAX_EXPERIENCE_MONTHS = 1200


class CandidateProfileRead(BaseModel):
    """Профиль кандидата в ответе API."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    desired_role: str
    city: str | None
    salary: Money | None
    schedule: str | None
    experience_months: int | None
    available_from: date | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_profile(cls, profile: CandidateProfile) -> "CandidateProfileRead":
        return cls(
            user_id=profile.user_id,
            desired_role=profile.desired_role,
            city=profile.city,
            salary=profile.salary,
            schedule=profile.schedule,
            experience_months=profile.experience_months,
            available_from=profile.available_from,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class CandidateProfileUpdateRequest(BaseModel):
    """Создание и изменение профиля.

    Поле, которого нет в запросе, не меняется. Явный `null` — осознанная
    очистка, поэтому допустим только для nullable-колонок. `user_id` в теле
    не принимается: кандидат определяется серверной сессией.
    """

    desired_role: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    salary: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    schedule: str | None = Field(default=None, max_length=100)
    experience_months: int | None = Field(
        default=None, ge=0, le=MAX_EXPERIENCE_MONTHS
    )
    available_from: date | None = None

    @field_validator("salary")
    @classmethod
    def _quantize_salary(cls, value: Decimal | None) -> Decimal | None:
        """Приводит сумму к масштабу колонки.

        Валидатор поля выполняется после ограничений `Field`, поэтому лишние
        знаки после запятой отклоняются как ошибка, а не округляются молча.
        """
        return quantize_money(value)

    @field_validator("desired_role")
    @classmethod
    def _require_non_empty(cls, value: str | None) -> str | None:
        """Колонка NOT NULL: очистить желаемую должность нельзя."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Желаемая должность не может быть пустой")
        return cleaned

    @field_validator("city", "schedule")
    @classmethod
    def _strip_or_clear(cls, value: str | None) -> str | None:
        """Пустая строка равна очистке поля: колонка это допускает."""
        if value is None:
            return None
        return value.strip() or None
