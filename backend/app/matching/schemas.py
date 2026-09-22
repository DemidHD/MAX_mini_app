"""Схемы ленты вакансий."""

from decimal import Decimal

from pydantic import BaseModel

from app.core.enums import CriterionType


class FeedCriterion(BaseModel):
    """Условие вакансии в карточке.

    Показываем сам факт условия, а не результат проверки кандидата:
    объяснимость подбора относится к P1 (раздел 64).
    """

    type: CriterionType
    required: bool
    value: dict | list | str | int | float | bool | None


class FeedVacancy(BaseModel):
    """Короткая карточка вакансии для ленты кандидата."""

    id: int
    title: str
    location: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    schedule: str | None
    criteria: list[FeedCriterion]


class FeedResponse(BaseModel):
    items: list[FeedVacancy]
    limit: int
    offset: int
    # Полное число подходящих опубликованных вакансий
    total: int
