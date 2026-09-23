"""Схемы отклика: первичный отбор, карточка кандидата, решение работодателя.

Разделы 18, 19, 20, 27, 33, 34, 35 тех-доки.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import (
    ApplicationStatus,
    CriterionType,
    DecisionAction,
    RejectReason,
    ScreeningQuestionType,
)
from app.core.money import Money

# Раздел 18: в P0 у вакансии 3–4 вопроса, в P1 — до 6. Предел здесь выше
# продуктового: он отсекает мусорное тело запроса, а не настраивает продукт.
MAX_SUBMITTED_ANSWERS = 50

# Ответ на вопрос первичного отбора. `bool` перечислен первым: он подкласс
# `int`, и порядок страхует от того, что «да» превратится в единицу.
AnswerValue = bool | int | float | str | None


class ScreeningQuestionRead(BaseModel):
    """Вопрос в том виде, в каком его показывают кандидату.

    `rules` — только то, что нужно, чтобы отрисовать поле и проверить ответ
    до отправки. Отсекающее условие вакансии сюда не попадает.
    """

    id: int
    question: str
    type: ScreeningQuestionType
    required: bool
    sort_order: int
    rules: dict[str, Any]


class ScreeningAnswerRead(BaseModel):
    """Сохранённый ответ кандидата."""

    question_id: int
    value: AnswerValue


class ScreeningAnswerSubmit(BaseModel):
    """Ответ в запросе. Отсутствующее значение равно «не отвечено»."""

    question_id: int
    value: AnswerValue = None


class ScreeningSubmitRequest(BaseModel):
    """Ответы отклика целиком: отбор проходится за один запрос."""

    answers: list[ScreeningAnswerSubmit] = Field(
        default_factory=list, max_length=MAX_SUBMITTED_ANSWERS
    )


class ScreeningStateResponse(BaseModel):
    """Состояние первичного отбора по отклику."""

    application_id: int
    vacancy_id: int
    status: ApplicationStatus
    # Отбор ещё можно пройти: повторная обработка отклика запрещена
    can_submit: bool
    questions: list[ScreeningQuestionRead]
    answers: list[ScreeningAnswerRead]


class ScreeningResultResponse(BaseModel):
    """Результат первичного отбора.

    Перечисляются только объективные условия из раздела 30: типы обязательных
    критериев вакансии и вопросы, ответ на которые не прошёл отсекающее
    условие. Объяснение подбора с числами и весами — P1 (раздел 64).
    """

    application_id: int
    status: ApplicationStatus
    failed_criteria: list[CriterionType]
    failed_questions: list[int]


class CardCriterionResult(BaseModel):
    """Результат обязательного фильтра по одному критерию вакансии.

    `passed = null` — проверить нечем: нужных данных нет в профиле либо
    значение критерия записано в неизвестном формате. Числа и веса не
    раскрываются: развёрнутая объяснимость — P1 (раздел 64).
    """

    type: CriterionType
    required: bool
    passed: bool | None


class CardScreeningAnswer(BaseModel):
    """Ответ кандидата на вопрос первичного отбора в карточке."""

    question_id: int
    question: str
    type: ScreeningQuestionType
    value: AnswerValue


class CandidateCard(BaseModel):
    """Стандартизированная карточка кандидата. Раздел 34 тех-доки.

    Раздел 34 перечисляет только рабочие факторы: имени, фамилии и фото в
    карточке нет — продуктовое ТЗ (п. 4.4) описывает её так же. Анонимность
    как отдельная функция — P1 (раздел 63).

    `city` — город кандидата: раздел 34 называет поле «location», но в
    профиле и в контракте `GET /api/candidate/profile` оно называется `city`.
    """

    application_id: int
    status: ApplicationStatus
    applied_at: datetime
    desired_role: str | None
    city: str | None
    salary: Money | None
    schedule: str | None
    experience_months: int | None
    available_from: date | None
    screening_answers: list[CardScreeningAnswer]
    hard_filters: list[CardCriterionResult]


class CandidateListResponse(BaseModel):
    """Страница списка кандидатов по вакансии."""

    items: list[CandidateCard]
    limit: int
    offset: int
    # Полное число кандидатов вакансии, прошедших первичный отбор
    total: int


class DecisionRequest(BaseModel):
    """Решение работодателя. Раздел 35 тех-доки.

    `reserved` разбирается схемой, но отклоняется сервисом: по разделу 20
    резерв относится к P1.
    """

    action: DecisionAction
    reject_reason: RejectReason | None = None


class DecisionResponse(BaseModel):
    """Результат решения работодателя."""

    application_id: int
    status: ApplicationStatus
    action: DecisionAction
    reject_reason: RejectReason | None
    decided_at: datetime


class ApplicationCreatedResponse(BaseModel):
    """Отклик кандидата на вакансию. Раздел 32 тех-доки.

    Возвращается и при повторном запросе: раздел 57 требует вернуть
    существующий отклик, а не ошибку. Отличить создание от повтора можно по
    коду ответа — `201` против `200`.
    """

    id: int
    vacancy_id: int
    status: ApplicationStatus
    created_at: datetime
