"""Объяснимость подбора для карточки кандидата. Раздел 64 тех-доки.

Вход — только результаты объективных критериев вакансии
(`app.matching.ranking.CriterionOutcome`), которые сами приходят из
`app.matching.rules`. Раздел 31: субъективные признаки (фото, пол, возраст,
«харизма» и т.п.) в подборе не участвуют и сюда попасть не могут — их просто
нет ни в одном источнике данных.
"""

from dataclasses import dataclass

from app.core.enums import CriterionType
from app.matching.ranking import CriterionOutcome


@dataclass(frozen=True)
class ExperienceExplanation:
    candidate: int | None
    required: int | None


@dataclass(frozen=True)
class MatchExplanation:
    matched: list[CriterionType]
    experience: ExperienceExplanation | None


def explain(
    outcomes: list[CriterionOutcome],
    *,
    experience_required_months: int | None,
    candidate_experience_months: int | None,
) -> MatchExplanation:
    """Раздел 64: список совпавших критериев и опыт — отдельной парой чисел.

    Опыт всегда выделяется отдельно, даже если он совпал: раздел 64 показывает
    его как пару "кандидат / требуется", а не флаг в общем списке. Блок
    заводится, только если в вакансии вообще есть критерий `experience` —
    без требования сравнивать опыт кандидата не с чем.
    """
    matched = [
        item.type
        for item in outcomes
        if item.passed and item.type != CriterionType.EXPERIENCE
    ]
    experience = None
    if experience_required_months is not None:
        experience = ExperienceExplanation(
            candidate=candidate_experience_months,
            required=experience_required_months,
        )
    return MatchExplanation(matched=matched, experience=experience)
