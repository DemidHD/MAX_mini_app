"""Проверка ответов первичного отбора.

Раздел 18 тех-доки задаёт у вопроса тип ответа и `validation_rules` —
«дополнительные правила проверки ответа». Конкретный состав правил тех-докой
не зафиксирован, поэтому он определён здесь как контракт с тем, кто создаёт
вопросы вакансии:

    общие       {"must_equal": <значение>} — отсекающее условие вакансии
    text        {"min_length": 1, "max_length": 500}
    number      {"min": 0, "max": 40}
    choice      {"options": ["да", "нет"]}

Разделение принципиальное:

- нарушение формата (не тот тип, длина, диапазон, вариант вне списка) —
  ошибка запроса, `422`;
- корректный ответ, не совпавший с `must_equal`, — бизнес-результат,
  отклик уходит в `hard_filter_failed`.

`must_equal` кандидату не показывается (см. `public_rules`): зная отсекающее
условие, ответ можно просто подогнать под него.

Через `must_equal` выражается и обязательный критерий `certificate`: в P0
сертификаты в профиле не хранятся, поэтому наличие документа подтверждается
на первичном отборе (раздел 16 и формат `vacancy_criteria.value` в
docs/api-contracts.md).
"""

import logging
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.enums import ScreeningQuestionType
from app.core.errors import ValidationError
from app.vacancies.models import ScreeningQuestion

logger = logging.getLogger("app.screening")

# Ответы уходят в JSONB. Предел нужен не колонке, а защите от мусорного тела
# запроса: осмысленный ответ на вопрос первичного отбора короче.
MAX_TEXT_ANSWER_LENGTH = 2000


@dataclass(frozen=True)
class AnswerCheck:
    """Итог проверки одного ответа."""

    question_id: int
    # Нормализованное значение: оно уходит в `screening_answers.value`
    value: Any
    # Ответ не удовлетворяет отсекающему условию вакансии
    blocks: bool


def stored_value(raw: Any) -> Any:
    """Разворачивает ответ из формата хранения `{"value": <ответ>}`."""
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw


def public_rules(question: ScreeningQuestion) -> dict[str, Any]:
    """Правила, которые можно показать кандидату.

    Нужны frontend, чтобы отрисовать поле ответа и проверить его до отправки.
    Отсекающее условие `must_equal` сюда не попадает.
    """
    rules = _rules(question)
    allowed = ("options", "min", "max", "min_length", "max_length")
    return {key: rules[key] for key in allowed if key in rules}


def check_answers(
    questions: list[ScreeningQuestion], submitted: dict[int, Any]
) -> list[AnswerCheck]:
    """Проверяет ответы на вопросы вакансии и нормализует их значения.

    `submitted` — значения по `question_id`; вопрос без ответа в словарь не
    попадает. Ошибки формата собираются по всем вопросам сразу, чтобы frontend
    подсветил все поля за один запрос, а не по одному на попытку.
    """
    checks: list[AnswerCheck] = []
    problems: list[dict[str, Any]] = []

    for question in questions:
        raw = submitted.get(question.id)
        if _is_blank(raw):
            if question.required:
                problems.append(_problem(question, "answer_required"))
                continue
            # Нет ответа — нечего и проверять: отсекающее условие
            # необязательного вопроса не срабатывает само по себе
            if "must_equal" in _rules(question):
                logger.warning(
                    "Отсекающее условие на необязательном вопросе %s не проверено",
                    question.id,
                )
            continue

        try:
            value = _normalize(question, raw)
        except _AnswerProblem as problem:
            problems.append(_problem(question, problem.code, problem.details))
            continue

        checks.append(
            AnswerCheck(
                question_id=question.id,
                value=value,
                blocks=not _satisfies_condition(question, value),
            )
        )

    if problems:
        raise ValidationError(
            "Ответы первичного отбора заполнены неверно",
            code="screening_answers_invalid",
            details=problems,
        )
    return checks


def _is_blank(raw: Any) -> bool:
    """Незаполненное поле формы: значения нет или пришла пустая строка."""
    if raw is None:
        return True
    return isinstance(raw, str) and not raw.strip()


def _problem(
    question: ScreeningQuestion, code: str, details: Any = None
) -> dict[str, Any]:
    problem: dict[str, Any] = {"question_id": question.id, "code": code}
    if details is not None:
        problem["details"] = details
    return problem


class _AnswerProblem(Exception):
    """Внутренний сигнал: ответ не проходит проверку формата."""

    def __init__(self, code: str, details: Any = None) -> None:
        self.code = code
        self.details = details
        super().__init__(code)


def _rules(question: ScreeningQuestion) -> dict[str, Any]:
    rules = question.validation_rules
    if isinstance(rules, dict):
        return rules
    if rules is not None:
        logger.warning("validation_rules вопроса %s не объект", question.id)
    return {}


def _normalize(question: ScreeningQuestion, raw: Any) -> Any:
    match question.type:
        case ScreeningQuestionType.TEXT:
            return _normalize_text(question, raw)
        case ScreeningQuestionType.NUMBER:
            return _normalize_number(question, raw)
        case ScreeningQuestionType.BOOLEAN:
            return _normalize_boolean(raw)
        case ScreeningQuestionType.CHOICE:
            return _normalize_choice(question, raw)
        case _:
            # Тип вопроса пишет только backend, поэтому это дефект данных,
            # а не ошибка кандидата: молча пропустить ответ нельзя
            logger.error("Неизвестный тип вопроса %s: %s", question.id, question.type)
            raise _AnswerProblem("question_type_unsupported")


def _normalize_text(question: ScreeningQuestion, raw: Any) -> str:
    """Пустая строка сюда не доходит: она считается отсутствием ответа."""
    if not isinstance(raw, str):
        raise _AnswerProblem("text_expected")
    value = raw.strip()

    rules = _rules(question)
    max_length = min(
        _to_int(rules.get("max_length")) or MAX_TEXT_ANSWER_LENGTH,
        MAX_TEXT_ANSWER_LENGTH,
    )
    if len(value) > max_length:
        raise _AnswerProblem("text_too_long", {"max_length": max_length})

    min_length = _to_int(rules.get("min_length"))
    if min_length is not None and len(value) < min_length:
        raise _AnswerProblem("text_too_short", {"min_length": min_length})
    return value


def _normalize_number(question: ScreeningQuestion, raw: Any) -> int | float:
    value = _to_number(raw)
    if value is None:
        raise _AnswerProblem("number_expected")

    rules = _rules(question)
    number = Decimal(str(value))

    minimum = _to_decimal(rules.get("min"))
    if minimum is not None and number < minimum:
        raise _AnswerProblem("number_too_small", {"min": rules["min"]})

    maximum = _to_decimal(rules.get("max"))
    if maximum is not None and number > maximum:
        raise _AnswerProblem("number_too_large", {"max": rules["max"]})
    return value


def _normalize_boolean(raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise _AnswerProblem("boolean_expected")
    return raw


def _normalize_choice(question: ScreeningQuestion, raw: Any) -> str:
    if not isinstance(raw, str):
        raise _AnswerProblem("choice_expected")
    value = raw.strip()
    if not value:
        raise _AnswerProblem("choice_expected")

    options = _options(question)
    if not options:
        # Вопрос с выбором, но без вариантов — дефект вакансии. Отклонять
        # кандидата за чужую ошибку нельзя, поэтому принимаем строку как есть
        logger.warning("У вопроса %s с выбором не заданы варианты", question.id)
        if len(value) > MAX_TEXT_ANSWER_LENGTH:
            raise _AnswerProblem(
                "text_too_long", {"max_length": MAX_TEXT_ANSWER_LENGTH}
            )
        return value

    for option in options:
        if option.strip().casefold() == value.casefold():
            # Возвращаем вариант в том виде, в каком его задала вакансия
            return option.strip()
    raise _AnswerProblem("choice_not_allowed", {"options": options})


def _options(question: ScreeningQuestion) -> list[str]:
    raw = _rules(question).get("options")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item.strip()]


def _satisfies_condition(question: ScreeningQuestion, value: Any) -> bool:
    """Проверяет отсекающее условие вакансии. Условия нет — ответ проходит."""
    rules = _rules(question)
    if "must_equal" not in rules:
        return True
    return _equals(value, rules["must_equal"])


def _equals(answer: Any, expected: Any) -> bool:
    if isinstance(answer, bool) or isinstance(expected, bool):
        # bool — подкласс int, поэтому сравнение чисел сюда пускать нельзя
        return answer is expected
    if isinstance(answer, str) and isinstance(expected, str):
        return answer.strip().casefold() == expected.strip().casefold()

    answer_number = _to_decimal(answer)
    expected_number = _to_decimal(expected)
    if answer_number is not None and expected_number is not None:
        return answer_number == expected_number

    logger.warning("Отсекающее условие несопоставимо с ответом")
    return answer == expected


def _to_number(value: Any) -> int | float | None:
    """Число из ответа. `True` — не единица: это ответ не того типа."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        return int(number) if number.is_integer() else number
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _to_int(value: Any) -> int | None:
    number = _to_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)
