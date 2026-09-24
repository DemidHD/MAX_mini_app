"""Схемы ленты вакансий."""

from pydantic import BaseModel

from app.core.enums import CriterionType
from app.core.money import Money


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
    salary_min: Money | None
    salary_max: Money | None
    schedule: str | None
    # Показывается как есть, без проверки живой ли ссылки (не из тех-доки):
    # синхронная проверка на каждую карточку в ленте была бы N внешних
    # запросов за один показ ленты. Проверка и переподбор — только при
    # открытии конкретной вакансии, `GET /vacancies/{id}`.
    image_url: str | None
    criteria: list[FeedCriterion]


class FeedResponse(BaseModel):
    items: list[FeedVacancy]
    limit: int
    offset: int
    # Полное число подходящих опубликованных вакансий
    total: int
