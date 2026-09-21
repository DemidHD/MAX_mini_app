"""Правила обязательной фильтрации. Разделы 30, 31 тех-доки."""

from datetime import date
from decimal import Decimal

import pytest

from app.candidates.models import CandidateProfile
from app.core.enums import CriterionType
from app.matching.rules import evaluate_vacancy, matches_required_criteria
from app.vacancies.models import Vacancy, VacancyCriterion


def _profile(**kwargs) -> CandidateProfile:
    defaults = {
        "desired_role": "Бариста",
        "city": "Москва",
        "salary": Decimal("70000"),
        "schedule": "full_time",
        "experience_months": 24,
        "available_from": date(2026, 10, 1),
    }
    return CandidateProfile(**(defaults | kwargs))


def _vacancy(**kwargs) -> Vacancy:
    defaults = {"title": "Бариста", "salary_max": Decimal("90000")}
    return Vacancy(**(defaults | kwargs))


def _criterion(type_: CriterionType, value: dict, required: bool = True):
    return VacancyCriterion(type=type_, required=required, value=value)


def _check(criterion, profile, vacancy=None) -> bool | None:
    results = evaluate_vacancy(vacancy or _vacancy(), [criterion], profile)
    return results[0].passed


# --- Локация ---


def test_matching_city_passes() -> None:
    assert _check(_criterion(CriterionType.LOCATION, {"city": "Москва"}), _profile())


def test_city_comparison_ignores_case_and_spaces() -> None:
    profile = _profile(city="  москва ")
    assert _check(_criterion(CriterionType.LOCATION, {"city": "Москва"}), profile)


def test_other_city_fails() -> None:
    profile = _profile(city="Казань")
    assert _check(_criterion(CriterionType.LOCATION, {"city": "Москва"}), profile) is False


def test_city_list_is_supported() -> None:
    profile = _profile(city="Химки")
    criterion = _criterion(CriterionType.LOCATION, {"cities": ["Москва", "Химки"]})
    assert _check(criterion, profile)


def test_city_missing_in_profile_is_not_checkable() -> None:
    profile = _profile(city=None)
    assert _check(_criterion(CriterionType.LOCATION, {"city": "Москва"}), profile) is None


# --- График ---


def test_schedule_match() -> None:
    criterion = _criterion(CriterionType.SCHEDULE, {"schedule": "full_time"})
    assert _check(criterion, _profile())


def test_schedule_mismatch() -> None:
    criterion = _criterion(CriterionType.SCHEDULE, {"schedule": "night_shift"})
    assert _check(criterion, _profile()) is False


# --- Зарплата ---


def test_expectations_within_vacancy_ceiling_pass() -> None:
    criterion = _criterion(CriterionType.SALARY, {"max": 80000})
    assert _check(criterion, _profile(salary=Decimal("75000")))


def test_expectations_above_ceiling_fail() -> None:
    criterion = _criterion(CriterionType.SALARY, {"max": 60000})
    assert _check(criterion, _profile(salary=Decimal("75000"))) is False


def test_salary_falls_back_to_vacancy_maximum() -> None:
    criterion = _criterion(CriterionType.SALARY, {})
    vacancy = _vacancy(salary_max=Decimal("50000"))
    assert _check(criterion, _profile(salary=Decimal("70000")), vacancy) is False


def test_salary_without_expectations_is_not_checkable() -> None:
    criterion = _criterion(CriterionType.SALARY, {"max": 60000})
    assert _check(criterion, _profile(salary=None)) is None


# --- Дата выхода ---


def test_candidate_ready_in_time_passes() -> None:
    criterion = _criterion(CriterionType.AVAILABLE_FROM, {"date": "2026-10-05"})
    assert _check(criterion, _profile(available_from=date(2026, 10, 1)))


def test_candidate_ready_too_late_fails() -> None:
    criterion = _criterion(CriterionType.AVAILABLE_FROM, {"date": "2026-09-25"})
    assert _check(criterion, _profile(available_from=date(2026, 10, 1))) is False


def test_broken_date_is_not_checkable() -> None:
    criterion = _criterion(CriterionType.AVAILABLE_FROM, {"date": "не дата"})
    assert _check(criterion, _profile()) is None


# --- Опыт ---


def test_sufficient_experience_passes() -> None:
    criterion = _criterion(CriterionType.EXPERIENCE, {"min_months": 12})
    assert _check(criterion, _profile(experience_months=24))


def test_insufficient_experience_fails() -> None:
    criterion = _criterion(CriterionType.EXPERIENCE, {"min_months": 36})
    assert _check(criterion, _profile(experience_months=24)) is False


# --- Сертификат ---


def test_certificate_is_deferred_to_screening() -> None:
    """В профиле сертификатов нет, поэтому в ленте условие не отсекает."""
    criterion = _criterion(CriterionType.CERTIFICATE, {"name": "медкнижка"})
    assert _check(criterion, _profile()) is None


# --- Итоговое решение ---


def test_optional_criterion_does_not_block() -> None:
    criterion = _criterion(CriterionType.LOCATION, {"city": "Казань"}, required=False)
    results = evaluate_vacancy(_vacancy(), [criterion], _profile(city="Москва"))

    assert results[0].passed is False
    assert matches_required_criteria(results) is True


def test_required_criterion_blocks() -> None:
    criterion = _criterion(CriterionType.LOCATION, {"city": "Казань"})
    results = evaluate_vacancy(_vacancy(), [criterion], _profile(city="Москва"))

    assert matches_required_criteria(results) is False


def test_uncheckable_criterion_does_not_block() -> None:
    criterion = _criterion(CriterionType.CERTIFICATE, {"name": "медкнижка"})
    results = evaluate_vacancy(_vacancy(), [criterion], _profile())

    assert matches_required_criteria(results) is True


def test_malformed_criterion_does_not_break_matching() -> None:
    """Критерий не той структуры не должен ронять подбор и прятать вакансию."""
    criterion = VacancyCriterion(
        type=CriterionType.SALARY, required=True, value=["не", "словарь"]
    )
    results = evaluate_vacancy(_vacancy(salary_max=None), [criterion], _profile())

    assert results[0].passed is None
    assert matches_required_criteria(results) is True


@pytest.mark.parametrize(
    "field",
    ["photo_url", "gender", "age", "charisma", "culture_fit"],
    ids=["фото", "пол", "возраст", "харизма", "culture fit"],
)
def test_forbidden_attributes_are_absent_from_profile(field: str) -> None:
    """Раздел 31: запрещённых признаков нет ни в профиле, ни в подборе."""
    assert not hasattr(CandidateProfile, field)
