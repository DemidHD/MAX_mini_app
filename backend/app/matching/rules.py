"""Проверка кандидата на соответствие обязательным критериям вакансии.

Раздел 30 тех-доки — объективные критерии подбора, раздел 31 — что
использовать запрещено. Модуль работает только с полями, перечисленными
в разделе 30, и ничего не знает о фото, поле, возрасте и субъективных
характеристиках: таких данных нет ни в профиле кандидата, ни здесь.

Формат `vacancy_criteria.value` (контракт с тем, кто создаёт вакансии):

    location        {"city": "Москва"} или {"cities": ["Москва", "Химки"]}
    schedule        {"schedule": "full_time"} или {"schedules": [...]}
    salary          {"max": 90000} — потолок вакансии; если ключа нет,
                    берётся vacancies.salary_max
    available_from  {"date": "2026-10-01"} — не позже этой даты
    experience      {"min_months": 12}
    certificate     {"name": "медкнижка"} — в P0 не проверяется по профилю,
                    подтверждается на первичном отборе

Значение `None` у результата проверки означает «проверить нечем»:
в профиле нет данных или критерий записан в неизвестном формате.
Такая вакансия из ленты не убирается — скрываем только то, что
действительно не подходит.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.candidates.models import CandidateProfile
from app.core.enums import CriterionType
from app.vacancies.models import Vacancy, VacancyCriterion

logger = logging.getLogger("app.matching")


@dataclass(frozen=True)
class CriterionResult:
    """Итог проверки одного критерия."""

    type: CriterionType
    required: bool
    # True — подходит, False — не подходит, None — проверить нечем
    passed: bool | None

    @property
    def blocks_feed(self) -> bool:
        """Обязательный критерий, по которому кандидат точно не проходит."""
        return self.required and self.passed is False


def evaluate_vacancy(
    vacancy: Vacancy,
    criteria: list[VacancyCriterion],
    profile: CandidateProfile | None,
) -> list[CriterionResult]:
    return [_evaluate(criterion, vacancy, profile) for criterion in criteria]


def matches_required_criteria(results: list[CriterionResult]) -> bool:
    return not any(result.blocks_feed for result in results)


def _evaluate(
    criterion: VacancyCriterion,
    vacancy: Vacancy,
    profile: CandidateProfile | None,
) -> CriterionResult:
    passed = None if profile is None else _check(criterion, vacancy, profile)
    return CriterionResult(
        type=criterion.type, required=criterion.required, passed=passed
    )


def _check(
    criterion: VacancyCriterion, vacancy: Vacancy, profile: CandidateProfile
) -> bool | None:
    value = criterion.value if isinstance(criterion.value, dict) else {}

    match criterion.type:
        case CriterionType.LOCATION:
            return _check_location(value, profile)
        case CriterionType.SCHEDULE:
            return _check_schedule(value, profile)
        case CriterionType.SALARY:
            return _check_salary(value, vacancy, profile)
        case CriterionType.AVAILABLE_FROM:
            return _check_available_from(value, profile)
        case CriterionType.EXPERIENCE:
            return _check_experience(value, profile)
        case CriterionType.CERTIFICATE:
            # Сертификаты не хранятся в профиле: вопрос задаётся на отборе
            return None
        case _:
            logger.warning("Неизвестный тип критерия: %s", criterion.type)
            return None


def _check_location(value: dict[str, Any], profile: CandidateProfile) -> bool | None:
    expected = _string_set(value, "city", "cities")
    if not expected or not profile.city:
        return None
    return _normalize(profile.city) in expected


def _check_schedule(value: dict[str, Any], profile: CandidateProfile) -> bool | None:
    expected = _string_set(value, "schedule", "schedules")
    if not expected or not profile.schedule:
        return None
    return _normalize(profile.schedule) in expected


def _check_salary(
    value: dict[str, Any], vacancy: Vacancy, profile: CandidateProfile
) -> bool | None:
    """Ожидания кандидата не должны превышать потолок вакансии.

    Потолок вакансии подставляется, только когда критерий его не задаёт.
    Если `max` задан, но прочитать его нельзя, проверять нечем: молча
    сравнивать с другим числом — значит менять смысл условия.
    """
    if "max" in value:
        limit = _to_decimal(value["max"])
    else:
        limit = _to_decimal(vacancy.salary_max)
    if limit is None or profile.salary is None:
        return None
    return profile.salary <= limit


def _check_available_from(
    value: dict[str, Any], profile: CandidateProfile
) -> bool | None:
    """Кандидат должен быть готов выйти не позже нужной даты."""
    deadline = _to_date(value.get("date"))
    if deadline is None or profile.available_from is None:
        return None
    return profile.available_from <= deadline


def _check_experience(value: dict[str, Any], profile: CandidateProfile) -> bool | None:
    minimum = _to_months(value.get("min_months"))
    if minimum is None or profile.experience_months is None:
        return None
    return profile.experience_months >= minimum


def _string_set(value: dict[str, Any], single_key: str, many_key: str) -> set[str]:
    """Собирает допустимые значения: критерий может задавать одно или список."""
    raw: list[Any] = []
    single = value.get(single_key)
    if isinstance(single, str):
        raw.append(single)
    many = value.get(many_key)
    if isinstance(many, list):
        raw.extend(many)
    return {_normalize(item) for item in raw if isinstance(item, str) and item.strip()}


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning("Некорректное числовое значение критерия")
        return None
    if not number.is_finite():
        logger.warning("Неконечное числовое значение критерия")
        return None
    return number


def _to_months(value: Any) -> int | None:
    """Число месяцев из критерия.

    `True` — не «один месяц»: булево значение в этом поле означает, что
    критерий заполнен неверно. Число в виде строки или с нулевой дробной
    частью принимаем: так его может прислать форма вакансии.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            logger.warning("Некорректное число месяцев в критерии")
            return None
    return None


def _to_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        pass
    try:
        # Форма могла прислать дату вместе со временем
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        logger.warning("Некорректная дата в критерии")
        return None
