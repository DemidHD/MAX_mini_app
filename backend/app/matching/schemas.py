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
    criteria: list[FeedCriterion]


class FeedResponse(BaseModel):
    items: list[FeedVacancy]
    limit: int
    offset: int
    # Сколько подходящих вакансий найдено среди просмотренных. Поиск
    # останавливается, как только набрана страница, поэтому это не счётчик
    # всех подходящих вакансий в базе
    total: int
    # Остались ли непросмотренные вакансии: страница может быть пустой,
    # а дальше в базе — подходящие
    has_more: bool
