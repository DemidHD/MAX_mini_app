"""Обучение на решениях работодателя. Функция 30 UX-карты (E07, режим P2).

«Причины отказов и решения меняют только порядок прошедших обязательные
фильтры» / «Меняет сортировку, интерфейс может не меняться» — поправка
входит только в ranking (`weight` желательного критерия), никогда в hard
filters: кандидат, не прошедший обязательное условие вакансии, в список
работодателя вообще не попадает (см. `REVIEWABLE_STATUSES` в
`app.applications.employer_service`) и до этого модуля не доходит.

Метод — статистика по решениям, а не ML: алгоритм нигде не описан (ни в
тех-доке, ни в UX-карте), а раздел 31 тех-доки запрещает решения по
субъективным/запрещённым признакам, так что чем проще и объяснимее правило,
тем безопаснее. Для каждого желательного критерия сравнивается доля
`invited` среди откликов, где критерий выполнен, и среди тех, где не
выполнен — тот же принцип, что и в синтетической калибровке
(`app.vacancies.calibration`), но на реальной истории решений.

Поправка используется только там, где работодатель ещё не задавал вес сам
(ни калибровкой, ни вручную) — см. `_criteria_context` в
`app.applications.employer_service`.
"""

import logging
from collections import defaultdict
from decimal import Decimal

from app.applications.models import EmployerDecision
from app.core.enums import CriterionType, DecisionAction

logger = logging.getLogger("app.matching.learning")

# Меньше наблюдений — поправка ненадёжна, лучше не трогать вес вовсе
MIN_SAMPLES = 3
MIN_WEIGHT = Decimal("0.2")
MAX_WEIGHT = Decimal("2.0")


async def learned_weight_adjustment(employer_id: int) -> dict[CriterionType, Decimal]:
    """Поправка веса по каждому желательному критерию, посчитанная по всей
    истории решений работодателя (по всем его вакансиям)."""
    decisions = await (
        EmployerDecision.filter(
            application__vacancy__employer_id=employer_id,
            action__in=[DecisionAction.INVITED, DecisionAction.REJECTED],
        ).select_related("application")
    )
    if not decisions:
        return {}

    matched_invited: dict[CriterionType, int] = defaultdict(int)
    matched_total: dict[CriterionType, int] = defaultdict(int)
    unmatched_invited: dict[CriterionType, int] = defaultdict(int)
    unmatched_total: dict[CriterionType, int] = defaultdict(int)

    for decision in decisions:
        snapshot = decision.application.hard_filter_result
        if not snapshot:
            continue
        invited = decision.action is DecisionAction.INVITED
        for criterion in snapshot.get("criteria", []):
            if criterion.get("required"):
                continue
            passed = criterion.get("passed")
            if passed is None:
                continue
            try:
                criterion_type = CriterionType(criterion.get("type"))
            except ValueError:
                continue
            if passed:
                matched_total[criterion_type] += 1
                if invited:
                    matched_invited[criterion_type] += 1
            else:
                unmatched_total[criterion_type] += 1
                if invited:
                    unmatched_invited[criterion_type] += 1

    adjustments: dict[CriterionType, Decimal] = {}
    for criterion_type in CriterionType:
        matched_n = matched_total[criterion_type]
        unmatched_n = unmatched_total[criterion_type]
        if matched_n < MIN_SAMPLES or unmatched_n < MIN_SAMPLES:
            continue
        matched_rate = Decimal(matched_invited[criterion_type]) / matched_n
        unmatched_rate = Decimal(unmatched_invited[criterion_type]) / unmatched_n
        weight = Decimal("1") + (matched_rate - unmatched_rate)
        adjustments[criterion_type] = min(max(weight, MIN_WEIGHT), MAX_WEIGHT)
    return adjustments
