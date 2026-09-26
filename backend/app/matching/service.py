"""Лента вакансий для кандидата. Раздел 30 тех-доки."""

import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from tortoise.query_utils import Prefetch

from app.applications.models import Application
from app.candidates.models import CandidateProfile
from app.core import cache
from app.core.config import settings
from app.core.enums import CriterionType, VacancyStatus
from app.matching.rules import evaluate_vacancy, matches_required_criteria
from app.matching.schemas import FeedCriterion, FeedResponse, FeedVacancy
from app.users.models import User
from app.vacancies.models import Vacancy, VacancyCriterion

logger = logging.getLogger("app.matching")

# Обязательные критерии считаются в Python. Читаем вакансии пакетами, но
# проходим всю выборку: иначе подходящие вакансии за первым окном терялись бы,
# а `total` зависел бы от внутреннего лимита сканирования.
FEED_SCAN_BATCH_SIZE = 200

# Не из тех-доки — техническая оптимизация. Опубликованные вакансии с их
# критериями — общий для всех кандидатов пул подбора: он один и тот же на
# каждое открытие ленты каждым кандидатом и меняется только решением
# работодателя (публикация/закрытие/правка), а не каждым запросом. Ключ один
# (не по кандидату): персональная часть подбора (профиль, уже поданные
# отклики) считается поверх кэша в Python, в БД не ходит.
_FEED_POOL_CACHE_KEY = "cache:feed:pool"


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

    pool = await _load_feed_pool()

    page: list[FeedVacancy] = []
    total = 0
    for entry in pool:
        if entry["id"] in applied_vacancy_ids:
            continue

        vacancy_like = SimpleNamespace(salary_max=_decimal(entry["salary_max"]))
        criteria_like = [
            SimpleNamespace(
                type=CriterionType(criterion["type"]),
                required=criterion["required"],
                value=criterion["value"],
            )
            for criterion in entry["criteria"]
        ]
        results = evaluate_vacancy(vacancy_like, criteria_like, profile)
        if not matches_required_criteria(results):
            continue

        if offset <= total < offset + limit:
            page.append(
                FeedVacancy(
                    id=entry["id"],
                    title=entry["title"],
                    location=entry["location"],
                    salary_min=_decimal(entry["salary_min"]),
                    salary_max=_decimal(entry["salary_max"]),
                    schedule=entry["schedule"],
                    image_url=entry["image_url"],
                    criteria=[
                        FeedCriterion(
                            type=CriterionType(criterion["type"]),
                            required=criterion["required"],
                            value=criterion["value"],
                        )
                        for criterion in entry["criteria"]
                    ],
                )
            )
        total += 1

    return FeedResponse(
        items=page,
        limit=limit,
        offset=offset,
        total=total,
    )


async def invalidate_feed_pool() -> None:
    """Вызывается из `app.vacancies.service` при любом изменении вакансии —
    публикации, правке, закрытии, подборе фото. Инвалидация всегда полная,
    без разбора «изменилось ли то, что действительно влияет на подбор»:
    вакансии меняются заметно реже, чем читается лента, а отдельная логика
    частичной инвалидации не стоит своей сложности при таком соотношении."""
    await cache.delete(_FEED_POOL_CACHE_KEY)


async def _load_feed_pool() -> list[dict[str, Any]]:
    cached = await cache.get_json(_FEED_POOL_CACHE_KEY)
    if cached is not None:
        return cached

    pool: list[dict[str, Any]] = []
    vacancies_query = Vacancy.filter(status=VacancyStatus.PUBLISHED).order_by(
        "-created_at", "-id"
    )
    scanned = 0
    while True:
        vacancies = await (
            vacancies_query.offset(scanned)
            .limit(FEED_SCAN_BATCH_SIZE)
            .prefetch_related(_known_criteria())
        )
        if not vacancies:
            break

        for vacancy in vacancies:
            pool.append(
                {
                    "id": vacancy.id,
                    "title": vacancy.title,
                    "location": vacancy.location,
                    "salary_min": _str(vacancy.salary_min),
                    "salary_max": _str(vacancy.salary_max),
                    "schedule": vacancy.schedule,
                    "image_url": vacancy.image_url,
                    "criteria": [
                        {
                            "type": criterion.type.value,
                            "required": criterion.required,
                            "value": criterion.value,
                        }
                        for criterion in vacancy.criteria
                    ],
                }
            )

        scanned += len(vacancies)
        if len(vacancies) < FEED_SCAN_BATCH_SIZE:
            break

    await cache.set_json(_FEED_POOL_CACHE_KEY, pool, settings.cache_feed_pool_ttl_seconds)
    return pool


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


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
