"""Схемы разбора вакансии текстом/голосом через ИИ. Раздел 58 тех-доки.

`ParsedVacancyDraft` намеренно полностью необязательный: продуктовое ТЗ (п.
5.1) показывает результат на экране подтверждения, где работодатель правит
каждое поле, а не публикует вакансию автоматически. Раздел 57 запрещает
именно автопубликацию — этим требование и выполняется, отдельная логика на
случай "невалидного JSON" сверх пустого черновика не нужна.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import CriterionType, ScreeningQuestionType

MAX_VACANCY_TEXT_LENGTH = 4000


class ParsedCriterionDraft(BaseModel):
    """Условие вакансии, извлечённое ИИ. Формат `value` — как в разделе 16."""

    type: CriterionType
    required: bool = False
    value: dict = Field(default_factory=dict)


class ParsedQuestionDraft(BaseModel):
    """Вопрос первичного отбора, извлечённый ИИ."""

    question: str
    type: ScreeningQuestionType = ScreeningQuestionType.TEXT


class ParsedVacancyDraft(BaseModel):
    """Черновик вакансии для экрана подтверждения. Поля соответствуют
    `VacancyCreateRequest`, но без валидации диапазонов: это подсказка,
    а не готовые к сохранению данные — их ещё проверит форма."""

    title: str | None = None
    company_name: str | None = None
    description: str | None = None
    location: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    schedule: str | None = None
    criteria: list[ParsedCriterionDraft] = Field(default_factory=list)
    questions: list[ParsedQuestionDraft] = Field(default_factory=list)


class ParseVacancyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_VACANCY_TEXT_LENGTH)


class ParseVacancyResponse(BaseModel):
    """`ai_available=False` — раздел 57: ни один провайдер не ответил,
    frontend должен переключиться на обычную форму вакансии (P0). `True` при
    пустом `parsed` означает другое: провайдер ответил, но извлечь поля не
    удалось — экран подтверждения открывается пустым, а не рушится.

    `rejected=True` — не из тех-доки, продуктовое требование: текст описывает
    деятельность, запрещённую законодательством РФ (проституция, оборот
    наркотиков и т.п.). Это эвристика уровня ИИ-провайдера, а не техническая
    гарантия — она защищает только этот путь создания вакансии, не ручную
    форму. `parsed` в этом случае всегда пустой."""

    parsed: ParsedVacancyDraft
    source_text: str
    provider: str | None
    ai_available: bool
    rejected: bool = False
    rejection_reason: str | None = None


class TranscribeVacancyResponse(BaseModel):
    """`text=""`, `provider=None` — распознать не удалось (раздел 57)."""

    text: str
    provider: str | None


class ResumeParsedDraft(BaseModel):
    """Черновик профиля кандидата, извлечённый из резюме (экран C11
    UX-карты, функция 29). Поля соответствуют `CandidateProfileUpdateRequest`
    без валидации диапазонов — как и `ParsedVacancyDraft`, это подсказка,
    сохраняется только через подтверждённый `PATCH /candidate/profile`."""

    desired_role: str | None = None
    city: str | None = None
    salary: Decimal | None = None
    schedule: str | None = None
    experience_months: int | None = None
    available_from: str | None = None


class ParseResumeResponse(BaseModel):
    """`resume parse result никогда не сохраняется как истина без
    подтверждения» (UX-карта, C11) — черновик всегда возвращается в ответе,
    профиль кандидата этот вызов не трогает."""

    parsed: ResumeParsedDraft
    provider: str | None
    ai_available: bool
