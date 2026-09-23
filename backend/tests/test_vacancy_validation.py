"""Проверка условий вакансии и правил вопросов. Разделы 16, 18 тех-доки.

Модульные тесты без базы и HTTP: здесь важна каждая ветка разбора, потому
что от неё зависит, сможет ли подбор прочитать условие. Интеграция тех же
правил с эндпоинтом вакансии — в `test_vacancies.py`.

Правило простое: всё, что принято здесь, обязано читаться модулями
`app.matching.rules` и `app.applications.screening`, а всё, что они прочитать
не смогут, обязано быть отклонено.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.candidates.models import CandidateProfile
from app.core.enums import CriterionType, ScreeningQuestionType
from app.core.errors import ValidationError
from app.matching.rules import evaluate_vacancy
from app.vacancies.models import Vacancy, VacancyCriterion
from app.vacancies.schemas import CriterionWrite, ScreeningQuestionWrite
from app.vacancies.validation import validate_criteria, validate_questions


def _criterion(criterion_type: str, value: dict[str, Any]) -> CriterionWrite:
    return CriterionWrite(type=criterion_type, required=True, value=value)


def _question(
    question_type: str,
    rules: dict[str, Any] | None = None,
    *,
    required: bool = True,
) -> ScreeningQuestionWrite:
    return ScreeningQuestionWrite(
        question="Вопрос",
        type=question_type,
        required=required,
        validation_rules=rules,
    )


def _criterion_error(
    criterion: CriterionWrite, *, salary_max: Decimal | None = None
) -> dict[str, Any]:
    with pytest.raises(ValidationError) as failure:
        validate_criteria([criterion], vacancy_salary_max=salary_max)
    assert failure.value.code == "vacancy_criteria_invalid"
    return failure.value.details[0]


def _question_error(question: ScreeningQuestionWrite) -> dict[str, Any]:
    with pytest.raises(ValidationError) as failure:
        validate_questions([question])
    assert failure.value.code == "screening_questions_invalid"
    return failure.value.details[0]


# --- Условия вакансии: допустимые значения ----------------------------------


@pytest.mark.parametrize(
    ("criterion_type", "value"),
    [
        (CriterionType.LOCATION, {"city": "Москва"}),
        (CriterionType.LOCATION, {"cities": ["Москва", "Химки"]}),
        (CriterionType.LOCATION, {"city": "Москва", "cities": ["Химки"]}),
        (CriterionType.SCHEDULE, {"schedule": "full_time"}),
        (CriterionType.SCHEDULE, {"schedules": ["full_time", "shift"]}),
        (CriterionType.SALARY, {"max": 90000}),
        (CriterionType.SALARY, {"max": "90000.50"}),
        (CriterionType.SALARY, {"max": 0}),
        (CriterionType.AVAILABLE_FROM, {"date": "2026-10-01"}),
        (CriterionType.AVAILABLE_FROM, {"date": "2026-10-01T10:00:00"}),
        (CriterionType.EXPERIENCE, {"min_months": 12}),
        (CriterionType.EXPERIENCE, {"min_months": "12"}),
        (CriterionType.EXPERIENCE, {"min_months": 12.0}),
        (CriterionType.EXPERIENCE, {"min_months": 0}),
        (CriterionType.CERTIFICATE, {"name": "медкнижка"}),
    ],
)
def test_valid_criteria_are_accepted(criterion_type: str, value: dict) -> None:
    validate_criteria([_criterion(criterion_type, value)], vacancy_salary_max=None)


def test_salary_criterion_without_max_uses_vacancy_ceiling() -> None:
    validate_criteria(
        [_criterion(CriterionType.SALARY, {})], vacancy_salary_max=Decimal("90000")
    )


def test_empty_criteria_list_is_accepted() -> None:
    """Вакансия без формализованных условий — это нормально."""
    validate_criteria([], vacancy_salary_max=None)


# --- Условия вакансии: отклоняемые значения ---------------------------------


@pytest.mark.parametrize(
    ("criterion_type", "value", "code"),
    [
        # Опечатка в ключе превратила бы фильтр в ничто
        (CriterionType.LOCATION, {"cityy": "Москва"}, "unknown_keys"),
        (CriterionType.LOCATION, {}, "value_required"),
        (CriterionType.LOCATION, {"cities": "Москва"}, "list_expected"),
        (CriterionType.LOCATION, {"city": 42}, "non_empty_string_expected"),
        (CriterionType.LOCATION, {"city": "   "}, "non_empty_string_expected"),
        (CriterionType.LOCATION, {"cities": ["Москва", ""]}, "non_empty_string_expected"),
        (CriterionType.SCHEDULE, {"shift": "ночь"}, "unknown_keys"),
        (CriterionType.SCHEDULE, {"schedules": []}, "value_required"),
        (CriterionType.SALARY, {"min": 1000}, "unknown_keys"),
        (CriterionType.SALARY, {"max": "много"}, "number_expected"),
        (CriterionType.SALARY, {"max": True}, "number_expected"),
        (CriterionType.SALARY, {"max": -1}, "negative_number"),
        (CriterionType.AVAILABLE_FROM, {"day": "2026-10-01"}, "unknown_keys"),
        (CriterionType.AVAILABLE_FROM, {"date": "01.10.2026"}, "date_expected"),
        (CriterionType.AVAILABLE_FROM, {"date": 20261001}, "date_expected"),
        (CriterionType.AVAILABLE_FROM, {}, "date_expected"),
        (CriterionType.EXPERIENCE, {"months": 12}, "unknown_keys"),
        (CriterionType.EXPERIENCE, {"min_months": "полгода"}, "integer_expected"),
        (CriterionType.EXPERIENCE, {"min_months": 1.5}, "integer_expected"),
        (CriterionType.EXPERIENCE, {"min_months": True}, "integer_expected"),
        (CriterionType.EXPERIENCE, {"min_months": -1}, "negative_number"),
        (CriterionType.CERTIFICATE, {"title": "медкнижка"}, "unknown_keys"),
        (CriterionType.CERTIFICATE, {"name": ""}, "non_empty_string_expected"),
        (CriterionType.CERTIFICATE, {"name": 1}, "non_empty_string_expected"),
    ],
)
def test_invalid_criteria_are_rejected(
    criterion_type: str, value: dict, code: str
) -> None:
    problem = _criterion_error(_criterion(criterion_type, value))

    assert problem["code"] == code
    assert problem["type"] == criterion_type
    assert problem["index"] == 0


def test_salary_criterion_without_any_limit_is_rejected() -> None:
    """Ни `max`, ни потолка вакансии — проверять условию нечего."""
    problem = _criterion_error(_criterion(CriterionType.SALARY, {}), salary_max=None)

    assert problem["code"] == "salary_limit_required"


def test_all_broken_criteria_are_reported_at_once() -> None:
    """Форма должна подсветить все ошибки сразу, а не по одной на попытку."""
    with pytest.raises(ValidationError) as failure:
        validate_criteria(
            [
                _criterion(CriterionType.LOCATION, {"city": "Москва"}),
                _criterion(CriterionType.EXPERIENCE, {"min_months": -1}),
                _criterion(CriterionType.CERTIFICATE, {"name": ""}),
            ],
            vacancy_salary_max=None,
        )

    assert [item["index"] for item in failure.value.details] == [1, 2]


# --- Правила вопросов отбора ------------------------------------------------


@pytest.mark.parametrize(
    ("question_type", "rules"),
    [
        (ScreeningQuestionType.TEXT, None),
        (ScreeningQuestionType.TEXT, {"min_length": 1, "max_length": 500}),
        (ScreeningQuestionType.TEXT, {"must_equal": "да"}),
        (ScreeningQuestionType.NUMBER, {"min": 0, "max": 40}),
        (ScreeningQuestionType.NUMBER, {"must_equal": 12, "min": 0, "max": 24}),
        (ScreeningQuestionType.BOOLEAN, {"must_equal": True}),
        (ScreeningQuestionType.BOOLEAN, None),
        (ScreeningQuestionType.CHOICE, {"options": ["да", "нет"]}),
        (
            ScreeningQuestionType.CHOICE,
            {"options": ["утро", "вечер"], "must_equal": "утро"},
        ),
    ],
)
def test_valid_question_rules_are_accepted(question_type: str, rules: dict) -> None:
    validate_questions([_question(question_type, rules)])


@pytest.mark.parametrize(
    ("question_type", "rules", "required", "code"),
    [
        (ScreeningQuestionType.TEXT, {"pattern": "^да$"}, True, "unknown_keys"),
        (ScreeningQuestionType.TEXT, {"options": ["да"]}, True, "rules_not_applicable"),
        (
            ScreeningQuestionType.TEXT,
            {"min_length": 10, "max_length": 5},
            True,
            "range_inverted",
        ),
        (
            ScreeningQuestionType.TEXT,
            {"min_length": -1},
            True,
            "non_negative_integer_expected",
        ),
        (
            ScreeningQuestionType.TEXT,
            {"max_length": 100000},
            True,
            "length_too_large",
        ),
        (ScreeningQuestionType.TEXT, {"must_equal": 1}, True, "string_expected"),
        (ScreeningQuestionType.NUMBER, {"min": "мало"}, True, "number_expected"),
        (ScreeningQuestionType.NUMBER, {"min": 10, "max": 5}, True, "range_inverted"),
        (
            ScreeningQuestionType.NUMBER,
            {"must_equal": "двенадцать"},
            True,
            "number_expected",
        ),
        (
            ScreeningQuestionType.NUMBER,
            {"must_equal": 5, "min": 10},
            True,
            "must_equal_out_of_range",
        ),
        (
            ScreeningQuestionType.NUMBER,
            {"must_equal": 50, "max": 10},
            True,
            "must_equal_out_of_range",
        ),
        (
            ScreeningQuestionType.NUMBER,
            {"options": ["1"]},
            True,
            "rules_not_applicable",
        ),
        (ScreeningQuestionType.BOOLEAN, {"must_equal": "да"}, True, "boolean_expected"),
        (ScreeningQuestionType.BOOLEAN, {"min": 1}, True, "rules_not_applicable"),
        (ScreeningQuestionType.CHOICE, None, True, "options_required"),
        (ScreeningQuestionType.CHOICE, {"options": []}, True, "options_required"),
        (ScreeningQuestionType.CHOICE, {"options": "да"}, True, "options_required"),
        (
            ScreeningQuestionType.CHOICE,
            {"options": ["да", "да"]},
            True,
            "duplicate_options",
        ),
        (
            ScreeningQuestionType.CHOICE,
            {"options": ["да", ""]},
            True,
            "non_empty_string_expected",
        ),
        (
            ScreeningQuestionType.CHOICE,
            {"options": ["да"], "must_equal": "нет"},
            True,
            "must_equal_not_in_options",
        ),
        (
            ScreeningQuestionType.CHOICE,
            {"options": [f"вариант {index}" for index in range(30)]},
            True,
            "too_many_options",
        ),
        (
            ScreeningQuestionType.CHOICE,
            {"options": ["а" * 500]},
            True,
            "option_too_long",
        ),
        # Отсекающее условие на необязательном вопросе не сработает
        (ScreeningQuestionType.BOOLEAN, {"must_equal": True}, False, "must_equal_requires_required"),
    ],
)
def test_invalid_question_rules_are_rejected(
    question_type: str, rules: dict | None, required: bool, code: str
) -> None:
    problem = _question_error(_question(question_type, rules, required=required))

    assert problem["code"] == code
    assert problem["index"] == 0


def test_all_broken_questions_are_reported_at_once() -> None:
    with pytest.raises(ValidationError) as failure:
        validate_questions(
            [
                _question(ScreeningQuestionType.BOOLEAN, {"must_equal": True}),
                _question(ScreeningQuestionType.CHOICE, None),
                _question(ScreeningQuestionType.NUMBER, {"min": 10, "max": 1}),
            ]
        )

    assert [item["index"] for item in failure.value.details] == [1, 2]


# --- Согласованность с подбором ---------------------------------------------


def test_accepted_criteria_are_readable_by_matching() -> None:
    """Принятое условие обязано читаться подбором, а не считаться непонятным.

    Это главное, ради чего валидация вообще существует: `matching.rules`
    молча пропускает непонятные значения, поэтому проверка на входе и разбор
    при подборе должны понимать одно и то же.
    """
    values = {
        CriterionType.LOCATION: {"city": "Москва"},
        CriterionType.SCHEDULE: {"schedule": "full_time"},
        CriterionType.SALARY: {"max": 90000},
        CriterionType.AVAILABLE_FROM: {"date": "2026-10-01"},
        CriterionType.EXPERIENCE: {"min_months": 12},
    }
    validate_criteria(
        [_criterion(criterion_type, value) for criterion_type, value in values.items()],
        vacancy_salary_max=None,
    )

    vacancy = Vacancy(id=1, employer_id=1, title="Бариста")
    profile = CandidateProfile(
        user_id=2,
        desired_role="Бариста",
        city="Москва",
        salary=Decimal("70000"),
        schedule="full_time",
        experience_months=24,
        available_from=date(2026, 9, 1),
    )
    criteria = [
        VacancyCriterion(id=index, vacancy_id=1, type=criterion_type, required=True, value=value)
        for index, (criterion_type, value) in enumerate(values.items(), start=1)
    ]

    results = evaluate_vacancy(vacancy, criteria, profile)

    # `None` означало бы «проверить нечем» — значит, условие записано так,
    # что подбор его не понял
    assert [result.passed for result in results] == [True, True, True, True, True]
