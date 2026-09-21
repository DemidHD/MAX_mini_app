"""Лента вакансий для кандидата. Раздел 30 тех-доки."""

import logging

from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import VacancyStatus
from app.matching.rules import evaluate_vacancy, matches_required_criteria
from app.matching.schemas import FeedCriterion, FeedResponse, FeedVacancy
from app.users.models import User
from app.vacancies.models import Vacancy

logger = logging.getLogger("app.matching")

# Сколько последних опубликованных вакансий просматриваем за один запрос.
# Обязательные критерии считаются в Python, поэтому окно ограничено.
FEED_SCAN_LIMIT = 500


async def get_feed(user: User, *, limit: int, offset: int) -> FeedResponse:
    """Опубликованные вакансии, которым кандидат объективно не противоречит.

    Из ленты убираются только те вакансии, по которым кандидат точно не
    проходит обязательный критерий. Если проверить критерий нечем — вакансия
    остаётся: показывать меньше, чем можно проверить простым правилом, продукт
    не требует.
    """
    profile = await CandidateProfile.get_or_none(user_id=user.user_id)
    if profile is None:
        # Без профиля подбирать не по чему: кандидат сначала заполняет профиль
        logger.info("Лента запрошена без профиля кандидата")
        return FeedResponse(items=[], limit=limit, offset=offset, total=0)

    applied_vacancy_ids = set(
        await Application.filter(candidate_id=user.user_id).values_list(
            "vacancy_id", flat=True
        )
    )

    vacancies = (
        await Vacancy.filter(status=VacancyStatus.PUBLISHED)
        .exclude(id__in=applied_vacancy_ids or [0])
        .order_by("-created_at")
        .limit(FEED_SCAN_LIMIT)
        .prefetch_related("criteria")
    )

    suitable: list[FeedVacancy] = []
    for vacancy in vacancies:
        criteria = list(vacancy.criteria)
        results = evaluate_vacancy(vacancy, criteria, profile)
        if not matches_required_criteria(results):
            continue
        suitable.append(
            FeedVacancy(
                id=vacancy.id,
                title=vacancy.title,
                location=vacancy.location,
                salary_min=vacancy.salary_min,
                salary_max=vacancy.salary_max,
                schedule=vacancy.schedule,
                criteria=[
                    FeedCriterion(
                        type=criterion.type,
                        required=criterion.required,
                        value=criterion.value,
                    )
                    for criterion in criteria
                ],
            )
        )

    return FeedResponse(
        items=suitable[offset : offset + limit],
        limit=limit,
        offset=offset,
        total=len(suitable),
    )
