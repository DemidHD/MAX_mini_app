"""Ранжирование прошедших кандидатов по желательным критериям. Разделы 59, 65 тех-доки.

Раздел 65: ranking сортирует список кандидатов, уже прошедших hard filters,
и не заменяет их — кандидат, проваливший обязательный критерий, до этого
модуля вообще не доходит (`hard_filter_failed` не входит в список
работодателя, см. `REVIEWABLE_STATUSES`).

Раздел 21 продуктового ТЗ ("Простое ранжирование") прямо запрещает "магические
проценты": числовой score — только внутренний ключ сортировки backend,
наружу отдаются X/Y совпадений (см. `app.matching.explain`).

Калибровка весов работодателем — P2 (раздел 66). До неё вес критерия без
явного значения считается равным 1: все желательные критерии равнозначны.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums import CriterionType

DEFAULT_WEIGHT = Decimal("1")


@dataclass(frozen=True)
class CriterionOutcome:
    """Итог одного критерия вакансии для конкретного кандидата."""

    type: CriterionType
    required: bool
    passed: bool | None


@dataclass(frozen=True)
class RankingResult:
    """`score` — ключ сортировки, `desirable_*` — то, что можно показать (X/Y)."""

    score: Decimal
    desirable_matched: int
    desirable_total: int


def rank(
    outcomes: list[CriterionOutcome], weights: dict[CriterionType, Decimal]
) -> RankingResult:
    """Взвешенная сумма прошедших желательных критериев.

    Обязательные критерии в скор не входят: кандидат либо прошёл их на
    отборе, либо в списке его вообще нет. `passed is None` ("проверить
    нечем") в совпадения не засчитывается, но и не штрафует — как в подборе
    (`app.matching.rules`) и первичном отборе.
    """
    desirable = [item for item in outcomes if not item.required]
    matched = [item for item in desirable if item.passed]
    score = sum(
        (weights.get(item.type, DEFAULT_WEIGHT) for item in matched), Decimal("0")
    )
    return RankingResult(
        score=score, desirable_matched=len(matched), desirable_total=len(desirable)
    )
