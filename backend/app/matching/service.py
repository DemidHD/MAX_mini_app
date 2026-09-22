"""Лента вакансий для кандидата. Раздел 30 тех-доки."""

import logging

from tortoise.query_utils import Prefetch

from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core.enums import CriterionType, VacancyStatus
from app.matching.rules import evaluate_vacancy, matches_required_criteria
from app.matching.schemas import FeedCriterion, FeedResponse, FeedVacancy
from app.users.models import User
from app.vacancies.models import Vacancy, VacancyCriterion

logger = logging.getLogger("app.matching")

# Обязательные критерии считаются в Python, поэтому вакансии читаются порциями.
FEED_BATCH_SIZE = 250
# Предел просмотра за один запрос: лента не должна вычитывать всю базу.
FEED_MAX_SCANNED = 2000


async def get_feed(user: User, *, limit: int, offset: int) -> FeedResponse:
    """Опубликованные вакансии, которым кандидат объективно не противоречит.

    Из ленты убираются только те вакансии, по которым кандидат точно не
    проходит обязательный критерий. Если проверить критерий нечем — вакансия
    остаётся: показывать меньше, чем можно проверить простым правилом, продукт
    не требует.

    Вакансии просматриваются порциями, пока не наберётся запрошенная страница
    или не будет исчерпан предел просмотра. `has_more` говорит frontend, что
    за просмотренным есть ещё вакансии, даже если страница получилась пустой.
    """
    profile = await CandidateProfile.get_or_none(user_id=user.user_id)
    if profile is None:
        # Без профиля подбирать не по чему: кандидат сначала заполняет профиль
        logger.info("Лента запрошена без профиля кандидата")
        return FeedResponse(
            items=[], limit=limit, offset=offset, total=0, has_more=False
        )

    applied_vacancy_ids = set(
        await Application.filter(candidate_id=user.user_id).values_list(
            "vacancy_id", flat=True
        )
    )

    # Вторым ключом сортировки идёт id: без него вакансии с одинаковым
    # created_at могут прийти в разном порядке и страницы разъедутся.
    published = (
        Vacancy.filter(status=VacancyStatus.PUBLISHED)
        .exclude(id__in=applied_vacancy_ids or [0])
        .order_by("-created_at", "-id")
    )

    needed = offset + limit
    suitable: list[FeedVacancy] = []
    scanned = 0
    exhausted = False

    while scanned < FEED_MAX_SCANNED and len(suitable) <= needed:
        take = min(FEED_BATCH_SIZE, FEED_MAX_SCANNED - scanned)
        batch = (
            await published.offset(scanned)
            .limit(take)
            .prefetch_related(_known_criteria())
        )
        scanned += len(batch)

        for vacancy in batch:
            criteria = list(vacancy.criteria)
            results = evaluate_vacancy(vacancy, criteria, profile)
            if not matches_required_criteria(results):
                continue
            suitable.append(_to_card(vacancy, criteria))

        if len(batch) < take:
            exhausted = True
            break

    if not exhausted and scanned >= FEED_MAX_SCANNED:
        logger.info("Лента просмотрела предел в %s вакансий", FEED_MAX_SCANNED)

    # Нашли больше, чем нужно этой странице, — следующая точно не пустая.
    # Иначе смотрим, осталось ли в базе непросмотренное.
    has_more = len(suitable) > needed or (not exhausted and scanned >= FEED_MAX_SCANNED)

    return FeedResponse(
        items=suitable[offset : offset + limit],
        limit=limit,
        offset=offset,
        total=len(suitable),
        has_more=has_more,
    )


def _known_criteria() -> Prefetch:
    """Читает только критерии известных типов.

    Значение типа вне `CriterionType` (например, оставшееся от более новой
    версии кода) иначе роняет чтение всей ленты, а не одну вакансию. Такой
    критерий подбор всё равно проверить не может, поэтому вакансия остаётся
    в ленте по общему правилу.
    """
    return Prefetch(
        "criteria",
        queryset=VacancyCriterion.filter(type__in=list(CriterionType)),
    )


def _to_card(vacancy: Vacancy, criteria: list[VacancyCriterion]) -> FeedVacancy:
    return FeedVacancy(
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
