"""Проверка условий вакансии и правил вопросов отбора.

Тех-дока задаёт для `vacancy_criteria.value` и `screening_questions.validation_rules`
тип (JSONB) и назначение, но не состав. Состав зафиксирован в
docs/api-contracts.md и читается двумя модулями: подбором
(`app.matching.rules`) и первичным отбором (`app.applications.screening`).

Оба читают значение мягко: непонятную запись они считают «проверить нечем» и
кандидата не отсекают. Это правильно в рантайме, но означает, что опечатка в
условии вакансии (`{"cityy": "Москва"}`) молча превращает обязательный
критерий в ничто. Поэтому здесь, на входе, проверка строгая: условие, которое
подбор не сможет прочитать, до базы не доходит.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.applications.screening import MAX_TEXT_ANSWER_LENGTH
from app.core.enums import CriterionType, ScreeningQuestionType
from app.core.errors import ValidationError
from app.vacancies.schemas import CriterionWrite, ScreeningQuestionWrite

# Ключи, которые понимает `app.applications.screening`
ALLOWED_RULE_KEYS = frozenset(
    {"must_equal", "options", "min", "max", "min_length", "max_length"}
)

MAX_OPTIONS = 20
MAX_OPTION_LENGTH = 200


def validate_criteria(
    criteria: list[CriterionWrite], *, vacancy_salary_max: Decimal | None
) -> None:
    """Проверяет условия вакансии. Ошибки собираются по всем сразу.

    `vacancy_salary_max` нужен критерию `salary`: по контракту он может не
    задавать потолок и опираться на поле вакансии. Если нет ни того, ни
    другого, проверять будет нечем — такое условие не принимается.
    """
    problems: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria):
        code, details = _criterion_problem(criterion, vacancy_salary_max)
        if code is not None:
            problem: dict[str, Any] = {"index": index, "type": criterion.type.value}
            problem["code"] = code
            if details is not None:
                problem["details"] = details
            problems.append(problem)

    if problems:
        raise ValidationError(
            "Условия вакансии заполнены неверно",
            code="vacancy_criteria_invalid",
            details=problems,
        )


def validate_questions(questions: list[ScreeningQuestionWrite]) -> None:
    """Проверяет вопросы первичного отбора. Ошибки собираются по всем сразу."""
    problems: list[dict[str, Any]] = []
    for index, question in enumerate(questions):
        code, details = _question_problem(question)
        if code is not None:
            problem: dict[str, Any] = {"index": index, "code": code}
            if details is not None:
                problem["details"] = details
            problems.append(problem)

    if problems:
        raise ValidationError(
            "Вопросы первичного отбора заполнены неверно",
            code="screening_questions_invalid",
            details=problems,
        )


def _criterion_problem(
    criterion: CriterionWrite, vacancy_salary_max: Decimal | None
) -> tuple[str | None, Any]:
    value = criterion.value

    match criterion.type:
        case CriterionType.LOCATION:
            return _string_criterion(value, "city", "cities")
        case CriterionType.SCHEDULE:
            return _string_criterion(value, "schedule", "schedules")
        case CriterionType.SALARY:
            return _salary_criterion(value, vacancy_salary_max)
        case CriterionType.AVAILABLE_FROM:
            return _available_from_criterion(value)
        case CriterionType.EXPERIENCE:
            return _experience_criterion(value)
        case CriterionType.CERTIFICATE:
            return _certificate_criterion(value)
        case _:  # pragma: no cover — тип ограничен enum
            return "criterion_type_unsupported", None


def _string_criterion(
    value: dict[str, Any], single_key: str, many_key: str
) -> tuple[str | None, Any]:
    unknown = _unknown_keys(value, {single_key, many_key})
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": [single_key, many_key]}

    items: list[Any] = []
    single = value.get(single_key)
    if single is not None:
        items.append(single)
    many = value.get(many_key)
    if many is not None:
        if not isinstance(many, list):
            return "list_expected", {"key": many_key}
        items.extend(many)

    if not items:
        return "value_required", {"expected": [single_key, many_key]}
    for item in items:
        if not isinstance(item, str) or not item.strip():
            return "non_empty_string_expected", {"expected": [single_key, many_key]}
    return None, None


def _salary_criterion(
    value: dict[str, Any], vacancy_salary_max: Decimal | None
) -> tuple[str | None, Any]:
    unknown = _unknown_keys(value, {"max"})
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": ["max"]}

    if "max" not in value:
        # Потолок берётся из вакансии; без него условие ничего не проверит
        if vacancy_salary_max is None:
            return "salary_limit_required", None
        return None, None

    limit = _to_decimal(value["max"])
    if limit is None:
        return "number_expected", {"key": "max"}
    if limit < 0:
        return "negative_number", {"key": "max"}
    return None, None


def _available_from_criterion(value: dict[str, Any]) -> tuple[str | None, Any]:
    unknown = _unknown_keys(value, {"date"})
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": ["date"]}
    if _to_date(value.get("date")) is None:
        return "date_expected", {"key": "date"}
    return None, None


def _experience_criterion(value: dict[str, Any]) -> tuple[str | None, Any]:
    unknown = _unknown_keys(value, {"min_months"})
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": ["min_months"]}

    months = _to_months(value.get("min_months"))
    if months is None:
        return "integer_expected", {"key": "min_months"}
    if months < 0:
        return "negative_number", {"key": "min_months"}
    return None, None


def _certificate_criterion(value: dict[str, Any]) -> tuple[str | None, Any]:
    unknown = _unknown_keys(value, {"name"})
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": ["name"]}

    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        return "non_empty_string_expected", {"key": "name"}
    return None, None


def _question_problem(question: ScreeningQuestionWrite) -> tuple[str | None, Any]:
    # Отсутствие правил — это пустой набор правил, а не «проверять нечего»:
    # вопросу с выбором варианты обязательны в любом случае
    rules = question.validation_rules or {}

    unknown = _unknown_keys(rules, ALLOWED_RULE_KEYS)
    if unknown:
        return "unknown_keys", {"keys": unknown, "expected": sorted(ALLOWED_RULE_KEYS)}

    if "must_equal" in rules and not question.required:
        # Отбор не проверяет отсекающее условие, если ответа нет: такой
        # вопрос выглядел бы фильтром, ничего не фильтруя
        return "must_equal_requires_required", None

    match question.type:
        case ScreeningQuestionType.TEXT:
            return _text_rules(rules)
        case ScreeningQuestionType.NUMBER:
            return _number_rules(rules)
        case ScreeningQuestionType.BOOLEAN:
            return _boolean_rules(rules)
        case ScreeningQuestionType.CHOICE:
            return _choice_rules(rules)
        case _:  # pragma: no cover — тип ограничен enum
            return "question_type_unsupported", None


def _text_rules(rules: dict[str, Any]) -> tuple[str | None, Any]:
    extra = _unknown_keys(rules, {"must_equal", "min_length", "max_length"})
    if extra:
        return "rules_not_applicable", {"keys": extra}

    lengths: dict[str, int] = {}
    for key in ("min_length", "max_length"):
        if key not in rules:
            continue
        length = _to_int(rules[key])
        if length is None or length < 0:
            return "non_negative_integer_expected", {"key": key}
        if length > MAX_TEXT_ANSWER_LENGTH:
            return "length_too_large", {"key": key, "max": MAX_TEXT_ANSWER_LENGTH}
        lengths[key] = length

    if (
        "min_length" in lengths
        and "max_length" in lengths
        and lengths["min_length"] > lengths["max_length"]
    ):
        return "range_inverted", {"keys": ["min_length", "max_length"]}

    if "must_equal" in rules and not isinstance(rules["must_equal"], str):
        return "string_expected", {"key": "must_equal"}
    return None, None


def _number_rules(rules: dict[str, Any]) -> tuple[str | None, Any]:
    extra = _unknown_keys(rules, {"must_equal", "min", "max"})
    if extra:
        return "rules_not_applicable", {"keys": extra}

    bounds: dict[str, Decimal] = {}
    for key in ("min", "max"):
        if key not in rules:
            continue
        bound = _to_decimal(rules[key])
        if bound is None:
            return "number_expected", {"key": key}
        bounds[key] = bound

    if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
        return "range_inverted", {"keys": ["min", "max"]}

    if "must_equal" in rules:
        expected = _to_decimal(rules["must_equal"])
        if expected is None:
            return "number_expected", {"key": "must_equal"}
        if "min" in bounds and expected < bounds["min"]:
            return "must_equal_out_of_range", {"key": "min"}
        if "max" in bounds and expected > bounds["max"]:
            return "must_equal_out_of_range", {"key": "max"}
    return None, None


def _boolean_rules(rules: dict[str, Any]) -> tuple[str | None, Any]:
    extra = _unknown_keys(rules, {"must_equal"})
    if extra:
        return "rules_not_applicable", {"keys": extra}
    if "must_equal" in rules and not isinstance(rules["must_equal"], bool):
        return "boolean_expected", {"key": "must_equal"}
    return None, None


def _choice_rules(rules: dict[str, Any]) -> tuple[str | None, Any]:
    extra = _unknown_keys(rules, {"must_equal", "options"})
    if extra:
        return "rules_not_applicable", {"keys": extra}

    options = rules.get("options")
    if not isinstance(options, list) or not options:
        # Без вариантов выбирать не из чего, и ответ нечем проверить
        return "options_required", None
    if len(options) > MAX_OPTIONS:
        return "too_many_options", {"max": MAX_OPTIONS}

    cleaned: list[str] = []
    for option in options:
        if not isinstance(option, str) or not option.strip():
            return "non_empty_string_expected", {"key": "options"}
        if len(option) > MAX_OPTION_LENGTH:
            return "option_too_long", {"max": MAX_OPTION_LENGTH}
        cleaned.append(option.strip())
    if len(set(cleaned)) != len(cleaned):
        return "duplicate_options", None

    if "must_equal" in rules:
        expected = rules["must_equal"]
        if not isinstance(expected, str) or expected.strip() not in cleaned:
            return "must_equal_not_in_options", None
    return None, None


def _unknown_keys(value: dict[str, Any], allowed: set[str] | frozenset[str]) -> list[str]:
    return sorted(key for key in value if key not in allowed)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = int(str(value).strip())
    except ValueError:
        return None
    return number


def _to_months(value: Any) -> int | None:
    """То же прочтение, что и у подбора: строка и целый float допустимы."""
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
            return None
    return None


def _to_date(value: Any) -> date | None:
    """То же прочтение, что и у подбора: ISO-дата или дата со временем."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        return None
