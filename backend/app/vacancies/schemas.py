"""Схемы вакансии. Разделы 15, 16, 18, 27, 28, 29, 52 тех-доки.

Ограничения полей повторяют колонки `vacancies`, `vacancy_criteria` и
`screening_questions`: значение, прошедшее валидацию схемы, обязано
записаться в БД без ошибки драйвера.

Содержательная проверка `value` критерия и `validation_rules` вопроса живёт
в `app.vacancies.validation`: она сверяется с тем, как эти значения читают
подбор (`app.matching.rules`) и первичный отбор (`app.applications.screening`),
чтобы работодатель не смог завести условие, которое ничего не проверяет.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import CriterionType, ScreeningQuestionType, VacancyStatus
from app.vacancies.calibration import MAX_PROFILES
from app.core.money import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    Money,
    quantize_money,
)

# Предел на число условий вакансии: колонке он не нужен, но отсекает
# мусорное тело запроса.
MAX_CRITERIA = 20

# Раздел 18: в P0 у вакансии 3–4 вопроса, в P1 — до 6. Схема разрешает
# верхнюю границу P1, продуктовое ограничение живёт в интерфейсе.
MAX_QUESTIONS = 6

MAX_QUESTION_LENGTH = 1000
MAX_COMPANY_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 4000

# NUMERIC(5, 2) у `vacancy_criteria.weight`
WEIGHT_MAX_DIGITS = 5
WEIGHT_DECIMAL_PLACES = 2


class CriterionWrite(BaseModel):
    """Условие вакансии в запросе. Раздел 16 тех-доки.

    `weight` используется только ranking (P1): обязательный критерий решается
    соответствием, а не весом.
    """

    type: CriterionType
    required: bool
    value: dict[str, Any]
    weight: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=WEIGHT_MAX_DIGITS,
        decimal_places=WEIGHT_DECIMAL_PLACES,
    )


class CriterionRead(BaseModel):
    """Условие вакансии в ответе."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: CriterionType
    required: bool
    value: Any
    weight: Decimal | None


class ScreeningQuestionWrite(BaseModel):
    """Вопрос первичного отбора в запросе. Раздел 18 тех-доки.

    Порядок вопросов задаётся порядком в списке — `sort_order` в теле не
    принимается, иначе форма могла бы прислать две разные истины о порядке.
    """

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    type: ScreeningQuestionType
    required: bool = True
    validation_rules: dict[str, Any] | None = None

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Текст вопроса не может быть пустым")
        return cleaned


class ScreeningQuestionRead(BaseModel):
    """Вопрос в ответе работодателю.

    Правила возвращаются целиком, включая отсекающее условие `must_equal`:
    это вакансия самого работодателя. Кандидату те же вопросы отдаются через
    `GET /api/applications/{id}/screening` без `must_equal`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    type: ScreeningQuestionType
    required: bool
    sort_order: int
    validation_rules: dict[str, Any] | None


class VacancyCreateRequest(BaseModel):
    """Создание вакансии. Раздел 28 тех-доки.

    `employer_id` в теле не принимается: работодатель определяется сессией.

    Вакансия создаётся черновиком. `status: "published"` допускается, если
    заполнено всё, что требует раздел 29, — это один запрос вместо двух для
    формы «создать и опубликовать».
    """

    title: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=MAX_COMPANY_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    location: str | None = Field(default=None, max_length=255)
    salary_min: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    salary_max: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    schedule: str | None = Field(default=None, max_length=100)
    status: VacancyStatus = VacancyStatus.DRAFT
    criteria: list[CriterionWrite] = Field(default_factory=list, max_length=MAX_CRITERIA)
    questions: list[ScreeningQuestionWrite] = Field(
        default_factory=list, max_length=MAX_QUESTIONS
    )

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Название вакансии не может быть пустым")
        return cleaned

    @field_validator("location", "schedule", "company_name", "description")
    @classmethod
    def _strip_or_clear(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("salary_min", "salary_max")
    @classmethod
    def _quantize(cls, value: Decimal | None) -> Decimal | None:
        return quantize_money(value)

    @field_validator("status")
    @classmethod
    def _closed_on_create_is_meaningless(cls, value: VacancyStatus) -> VacancyStatus:
        if value is VacancyStatus.CLOSED:
            raise ValueError("Создать сразу закрытую вакансию нельзя")
        return value

    @model_validator(mode="after")
    def _salary_range(self) -> "VacancyCreateRequest":
        _ensure_salary_range(self.salary_min, self.salary_max)
        return self


class VacancyUpdateRequest(BaseModel):
    """Изменение вакансии. Раздел 27 тех-доки.

    Поле, которого нет в запросе, не меняется. Явный `null` — осознанная
    очистка, поэтому допустим только для nullable-колонок.

    `criteria` и `questions` заменяются целиком: частичное изменение списка
    потребовало бы идентификаторов элементов в запросе, а форма вакансии
    всегда присылает набор условий полностью.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=MAX_COMPANY_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    location: str | None = Field(default=None, max_length=255)
    salary_min: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    salary_max: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    schedule: str | None = Field(default=None, max_length=100)
    status: VacancyStatus | None = None
    criteria: list[CriterionWrite] | None = Field(default=None, max_length=MAX_CRITERIA)
    questions: list[ScreeningQuestionWrite] | None = Field(
        default=None, max_length=MAX_QUESTIONS
    )

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            # Колонка NOT NULL: очистить название нельзя
            raise ValueError("Название вакансии не может быть пустым")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Название вакансии не может быть пустым")
        return cleaned

    @field_validator("location", "schedule", "company_name", "description")
    @classmethod
    def _strip_or_clear(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("salary_min", "salary_max")
    @classmethod
    def _quantize(cls, value: Decimal | None) -> Decimal | None:
        return quantize_money(value)

    @field_validator("status")
    @classmethod
    def _status_is_required_value(cls, value: VacancyStatus | None) -> VacancyStatus:
        if value is None:
            raise ValueError("Статус вакансии не может быть пустым")
        return value


class VacancyRead(BaseModel):
    """Вакансия в ответе API.

    `public_token`, `public_url` и `applications_count` возвращаются только
    владельцу: кандидату нужна сама вакансия, а не ссылка для распространения
    и не статистика чужого найма.
    """

    id: int
    employer_id: int
    title: str
    company_name: str | None
    description: str | None
    location: str | None
    salary_min: Money | None
    salary_max: Money | None
    schedule: str | None
    image_url: str | None
    status: VacancyStatus
    public_token: str | None
    public_url: str | None
    applications_count: int | None
    criteria: list[CriterionRead]
    questions: list[ScreeningQuestionRead]
    created_at: datetime
    updated_at: datetime


class VacancyListResponse(BaseModel):
    """Страница списка вакансий работодателя."""

    items: list[VacancyRead]
    limit: int
    offset: int
    total: int


class ReferralLinkRead(BaseModel):
    """Реферальная ссылка вакансии (экран R01 UX-карты, функция 32)."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    url: str
    created_at: datetime


class ReferralLinkListResponse(BaseModel):
    items: list[ReferralLinkRead]


class CalibrationCriterionRead(BaseModel):
    """Один критерий синтетической тестовой карточки калибровки (E17 UX-карты,
    функция 25). `value_label` — не персональные данные, а описание условия
    («Москва», «другой график»)."""

    type: CriterionType
    matches: bool
    value_label: str


class CalibrationProfileRead(BaseModel):
    """Синтетическая тестовая карточка. `pattern_token` возвращается в
    `POST` вместе с решением работодателя — сервер по нему же и считает вес,
    ничего не сохраняя между запросами."""

    pattern_token: str
    criteria: list[CalibrationCriterionRead]


class CalibrationProfilesResponse(BaseModel):
    profiles: list[CalibrationProfileRead]


class CalibrationVote(BaseModel):
    pattern_token: str
    fit: bool


class CalibrationSubmitRequest(BaseModel):
    votes: list[CalibrationVote] = Field(default_factory=list, max_length=MAX_PROFILES)


class CalibrationWeightsResponse(BaseModel):
    """Итоговые веса желательных критериев после калибровки."""

    weights: dict[CriterionType, Decimal]


class VacancyAnalyticsResponse(BaseModel):
    """Сводка аналитики по вакансии (экран E18 UX-карты, функция 33,
    раздел 69 тех-доки)."""

    vacancy_id: int
    applications_total: int
    passed_hard_filters: int
    invited: int
    mutual_interest: int
    interviews_booked: int
    # `None` — по вакансии ещё нет ни одного собеседования
    time_to_first_interview_seconds: int | None


def _ensure_salary_range(
    salary_min: Decimal | None, salary_max: Decimal | None
) -> None:
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise ValueError("Нижняя граница зарплаты выше верхней")
