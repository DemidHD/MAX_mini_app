"""Вакансия: создание, чтение, изменение и публикация.

Разделы 15, 16, 18, 27, 28, 29 тех-доки.

Публикация выполняется через смену статуса в `PATCH /vacancies/{id}`:
отдельного эндпоинта раздел 27 не заводит, а состояние вакансии — такое же
поле, как остальные. Проверка обязательных данных перед публикацией —
раздел 29: неполная вакансия статус `published` не получает.
"""

import logging
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import BackgroundTasks
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import Application, EmployerDecision, Match
from app.applications.screening import public_rules
from app.core.config import settings
from app.core.enums import ApplicationStatus, DecisionAction, UserRole, VacancyStatus
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.interviews.models import Interview
from app.users.models import User
from app.vacancies import images
from app.vacancies import calibration
from app.vacancies.models import ReferralLink, ScreeningQuestion, Vacancy, VacancyCriterion
from app.vacancies.schemas import (
    CalibrationCriterionRead,
    CalibrationProfileRead,
    CalibrationProfilesResponse,
    CalibrationSubmitRequest,
    CalibrationWeightsResponse,
    CriterionRead,
    CriterionWrite,
    ReferralLinkListResponse,
    ReferralLinkRead,
    ScreeningQuestionRead,
    ScreeningQuestionWrite,
    VacancyAnalyticsResponse,
    VacancyCreateRequest,
    VacancyListResponse,
    VacancyRead,
    VacancyUpdateRequest,
)
from app.vacancies.validation import validate_criteria, validate_questions

logger = logging.getLogger("app.vacancies")

# Раздел 15: колонка `public_token` — VARCHAR(32)
PUBLIC_TOKEN_BYTES = 24
PUBLIC_TOKEN_ATTEMPTS = 3

# Раздел 24: колонка `referral_links.code` — VARCHAR(100)
REFERRAL_CODE_BYTES = 8
REFERRAL_CODE_ATTEMPTS = 3

# Раздел 29: без этих данных вакансия не публикуется
PUBLICATION_REQUIRED_FIELDS = ("title", "location", "salary", "schedule")

ALLOWED_VACANCY_TRANSITIONS: dict[VacancyStatus, frozenset[VacancyStatus]] = {
    # Закрыть можно и черновик: работодатель мог передумать
    VacancyStatus.DRAFT: frozenset({VacancyStatus.PUBLISHED, VacancyStatus.CLOSED}),
    # Снять с публикации обратно в черновик нельзя: по опубликованной вакансии
    # уже могли прийти отклики, и «черновик с откликами» ничего не значит.
    # Чтобы перестать набирать, вакансия закрывается.
    VacancyStatus.PUBLISHED: frozenset({VacancyStatus.CLOSED}),
    VacancyStatus.CLOSED: frozenset({VacancyStatus.PUBLISHED}),
}


async def get_own_vacancy(user: User, vacancy_id: int) -> Vacancy:
    """Вакансия текущего работодателя.

    Чужая вакансия — `404`, а не `403`: существование чужих вакансий наружу
    не раскрывается.
    """
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None or vacancy.employer_id != user.user_id:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    return vacancy


async def create_vacancy(
    user: User, payload: VacancyCreateRequest, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Создаёт вакансию работодателя (раздел 28).

    Условия и вопросы отбора создаются тем же запросом: по отдельности
    вакансия жила бы в состоянии «опубликована, но ничего не проверяет».

    Всё пишется одной транзакцией — иначе при сбое осталась бы вакансия без
    условий, и обязательная фильтрация тихо пропускала бы всех.
    """
    validate_criteria(payload.criteria, vacancy_salary_max=payload.salary_max)
    validate_questions(payload.questions)

    published = payload.status is VacancyStatus.PUBLISHED
    if published:
        _ensure_publishable(
            title=payload.title,
            location=payload.location,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            schedule=payload.schedule,
        )
    else:
        await _ensure_draft_limit(user)

    async with in_transaction() as connection:
        vacancy = await Vacancy.create(
            employer_id=user.user_id,
            title=payload.title,
            company_name=payload.company_name,
            description=payload.description,
            location=payload.location,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            schedule=payload.schedule,
            status=payload.status,
            public_token=await _new_public_token(connection) if published else None,
            using_db=connection,
        )
        await _replace_criteria(vacancy.id, payload.criteria, connection=connection)
        await _replace_questions(vacancy.id, payload.questions, connection=connection)

    # В фоне, после ответа: внешний HTTP-запрос к Openverse не должен ни
    # держать открытое соединение к БД, ни задерживать ответ — раздел 83
    # запрещает делать внешний сервис обязательным на пути P0. Первый ответ
    # уходит без фото, следующее открытие карточки увидит уже найденное.
    background_tasks.add_task(_assign_image, vacancy)

    await analytics.log_event(
        "vacancy_created",
        user_id=user.user_id,
        payload={"vacancy_id": vacancy.id, "status": vacancy.status.value},
    )
    if published:
        await analytics.log_event(
            "vacancy_published",
            user_id=user.user_id,
            payload={"vacancy_id": vacancy.id},
        )
    logger.info("Создана вакансия %s со статусом %s", vacancy.id, vacancy.status.value)
    return await _read(vacancy, owner=True)


async def get_vacancy(
    user: User, vacancy_id: int, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Вакансия по идентификатору (раздел 27).

    Работодатель видит только свои вакансии в любом статусе, кандидат —
    опубликованные и те, на которые уже откликнулся: иначе закрытая вакансия
    исчезала бы из его собственного отклика вместе с историей.
    """
    if user.role is UserRole.EMPLOYER:
        return await _read(
            await get_own_vacancy(user, vacancy_id),
            owner=True,
            background_tasks=background_tasks,
        )
    if user.role is UserRole.CANDIDATE:
        return await _read(
            await _visible_vacancy(user, vacancy_id),
            owner=False,
            background_tasks=background_tasks,
        )
    # До выбора роли доступны только onboarding-эндпоинты (раздел 12)
    raise ForbiddenError("Сначала нужно выбрать роль", code="role_not_selected")


async def _visible_vacancy(user: User, vacancy_id: int) -> Vacancy:
    """Вакансия, которую вправе открыть кандидат.

    Черновик и чужой найм — `404`. Снятая с публикации вакансия остаётся
    видимой тому, кто на неё откликнулся: его отклик, интервью и статусы
    никуда не делись.
    """
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    if vacancy.status is VacancyStatus.PUBLISHED:
        return vacancy

    applied = await Application.filter(
        vacancy_id=vacancy.id, candidate_id=user.user_id
    ).exists()
    if not applied:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    return vacancy


async def get_vacancy_by_public_token(
    user: User, token: str, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Вакансия по публичной ссылке (раздел 15): тот же вид, что кандидат
    получает по `GET /vacancies/{id}`. Роль смотрящего не важна — ссылку
    могут переслать кому угодно внутри MAX; важно только то же условие
    видимости, что и у обычной карточки: вакансия опубликована, либо
    смотрящий на неё уже откликался.
    """
    vacancy = await Vacancy.get_or_none(public_token=token)
    if vacancy is None:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    if vacancy.status is not VacancyStatus.PUBLISHED:
        applied = await Application.filter(
            vacancy_id=vacancy.id, candidate_id=user.user_id
        ).exists()
        if not applied:
            raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    return await _read(vacancy, owner=False, background_tasks=background_tasks)


async def delete_vacancy(user: User, vacancy_id: int) -> None:
    """Удаляет черновик вакансии.

    Только черновик: по опубликованной или закрытой вакансии уже могли
    прийти отклики, и удаление стёрло бы их историю (раздел 83 — исторические
    данные отклика не удаляются). Чтобы перестать набирать, вакансия
    закрывается через `PATCH`, а не удаляется.
    """
    vacancy = await get_own_vacancy(user, vacancy_id)
    if vacancy.status is not VacancyStatus.DRAFT:
        raise ConflictError(
            "Удалить можно только черновик вакансии",
            code="vacancy_not_draft",
            details={"status": vacancy.status.value},
        )
    await vacancy.delete()
    logger.info("Черновик вакансии %s удалён работодателем %s", vacancy_id, user.user_id)


async def read_vacancy_for_candidate(
    vacancy: Vacancy, background_tasks: BackgroundTasks
) -> VacancyRead:
    """Вакансия в кандидатском виде — без владельческих полей.

    Для мест, где видимость вакансии уже проверена по другому правилу
    (например, по факту существующего отклика — см.
    `app.applications.service.get_application`), а не по обычному пути
    `GET /vacancies/{id}`.
    """
    return await _read(vacancy, owner=False, background_tasks=background_tasks)


async def list_own_vacancies(
    user: User, *, limit: int, offset: int
) -> VacancyListResponse:
    """Вакансии работодателя для его кабинета.

    Эндпоинта нет в разделе 27, но `current_step = employer_home` (раздел 7)
    без списка вакансий не на чем показать.
    """
    query = Vacancy.filter(employer_id=user.user_id)
    total = await query.count()
    # `-id` вторым ключом: у вакансий, созданных в одну миллисекунду, порядок
    # иначе не определён, и страницы могли бы перекрываться
    vacancies = await query.order_by("-created_at", "-id").offset(offset).limit(limit)

    return VacancyListResponse(
        items=await _read_many(vacancies, owner=True),
        limit=limit,
        offset=offset,
        total=total,
    )


async def update_vacancy(
    user: User, vacancy_id: int, payload: VacancyUpdateRequest
) -> VacancyRead:
    """Изменяет вакансию и, при смене статуса, публикует или закрывает её.

    Вакансия блокируется на время изменения: публикация проверяет полноту
    данных, и параллельный запрос не должен успеть их поменять между
    проверкой и записью.
    """
    vacancy = await get_own_vacancy(user, vacancy_id)
    changed = payload.model_fields_set
    fields = {
        name: getattr(payload, name)
        for name in (
            "title",
            "company_name",
            "description",
            "location",
            "salary_min",
            "salary_max",
            "schedule",
        )
        if name in changed
    }

    salary_min = fields.get("salary_min", vacancy.salary_min)
    salary_max = fields.get("salary_max", vacancy.salary_max)
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise ValidationError(
            "Нижняя граница зарплаты выше верхней", code="salary_range_invalid"
        )

    criteria = payload.criteria if "criteria" in changed else None
    questions = payload.questions if "questions" in changed else None
    if criteria is not None:
        validate_criteria(criteria, vacancy_salary_max=salary_max)
    if questions is not None:
        validate_questions(questions)

    target_status = payload.status if "status" in changed else None
    publishing = False

    async with in_transaction() as connection:
        locked = await (
            Vacancy.filter(id=vacancy.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        for name, value in fields.items():
            setattr(locked, name, value)

        if target_status is not None and target_status is not locked.status:
            _ensure_status_transition(locked.status, target_status)
            publishing = target_status is VacancyStatus.PUBLISHED
            if publishing:
                _ensure_publishable(
                    title=locked.title,
                    location=locked.location,
                    salary_min=locked.salary_min,
                    salary_max=locked.salary_max,
                    schedule=locked.schedule,
                )
                if locked.public_token is None:
                    # Раздел 15: токен выдаётся один раз при первой публикации
                    # и при повторной не меняется — иначе разосланная ссылка
                    # перестала бы работать
                    locked.public_token = await _new_public_token(connection)
            locked.status = target_status

        await locked.save(using_db=connection)

        if criteria is not None:
            await _replace_criteria(locked.id, criteria, connection=connection)
        if questions is not None:
            # Проверка отсюда, а не до транзакции: отклик мог появиться уже
            # после неё, и тогда замена удалила бы историю ответов
            await _ensure_questions_replaceable(locked, connection=connection)
            await _replace_questions(locked.id, questions, connection=connection)

    if publishing:
        await analytics.log_event(
            "vacancy_published",
            user_id=user.user_id,
            payload={"vacancy_id": locked.id},
        )
        logger.info("Вакансия %s опубликована", locked.id)

    return await _read(locked, owner=True)


def _ensure_status_transition(
    current: VacancyStatus, target: VacancyStatus
) -> None:
    if target not in ALLOWED_VACANCY_TRANSITIONS.get(current, frozenset()):
        # Раздел 57: недопустимый переход состояния — `409 Conflict`
        raise ConflictError(
            "Недопустимый переход статуса вакансии",
            code="invalid_vacancy_status_transition",
            details={"status": current.value, "target": target.value},
        )


async def _ensure_draft_limit(user: User) -> None:
    """Не более `VACANCY_DRAFT_LIMIT` черновиков на работодателя одновременно.

    Ограничение не из тех-доки — продуктовое решение против брошенных
    черновиков в кабинете. Публикация освобождает место: считаются только
    вакансии в `draft`. Проверка не атомарна (без блокировки на пользователя):
    при двух параллельных запросах лимит теоретически можно превысить на
    одну вакансию — цена отдельной блокировки того не стоит для
    некритичного продуктового ограничения на масштабе микробизнеса.
    """
    count = await Vacancy.filter(
        employer_id=user.user_id, status=VacancyStatus.DRAFT
    ).count()
    if count >= settings.vacancy_draft_limit:
        raise ConflictError(
            f"Достигнут лимит черновиков вакансий ({settings.vacancy_draft_limit})",
            code="draft_limit_reached",
            details={"limit": settings.vacancy_draft_limit},
        )


async def _assign_image(vacancy: Vacancy) -> None:
    """Подбирает фото по теме вакансии сразу при создании (не из тех-доки).

    Лучшее старание, как и с ИИ (раздел 57): ошибка поиска не должна мешать
    созданию вакансии — она просто останется без фото до следующего открытия
    карточки, где подбор попробуется ещё раз
    (`app.vacancies.images.ensure_fresh_image`). Уже найденное фото этот
    повторный подбор не трогает — оно назначается вакансии один раз.
    """
    image_url = await images.find_image(vacancy.title)
    if image_url:
        vacancy.image_url = image_url
        await vacancy.save(update_fields=["image_url", "updated_at"])


def _ensure_publishable(
    *,
    title: str | None,
    location: str | None,
    salary_min: Decimal | None,
    salary_max: Decimal | None,
    schedule: str | None,
) -> None:
    """Раздел 29: перед публикацией проверяются обязательные данные.

    Зарплата считается заполненной, если задана хотя бы одна из границ:
    «от 60 000» и «до 90 000» — одинаково понятные кандидату формулировки.
    """
    filled = {
        "title": bool(title and title.strip()),
        "location": bool(location and location.strip()),
        "salary": salary_min is not None or salary_max is not None,
        "schedule": bool(schedule and schedule.strip()),
    }
    missing = [name for name in PUBLICATION_REQUIRED_FIELDS if not filled[name]]
    if missing:
        raise ValidationError(
            "Для публикации не хватает обязательных данных",
            code="vacancy_incomplete",
            details={"missing": missing},
        )


async def _ensure_questions_replaceable(
    vacancy: Vacancy, *, connection: BaseDBAsyncClient
) -> None:
    """Вопросы нельзя менять, когда по вакансии уже есть отклики.

    Замена удалила бы вопросы, а вместе с ними каскадом и ответы кандидатов.
    Раздел 83 прямо запрещает удалять исторические данные отклика.
    """
    if await Application.filter(vacancy_id=vacancy.id).using_db(connection).exists():
        raise ConflictError(
            "По вакансии уже есть отклики: вопросы отбора менять нельзя",
            code="vacancy_has_applications",
            details={"vacancy_id": vacancy.id},
        )


async def _replace_criteria(
    vacancy_id: int, criteria: list[CriterionWrite], *, connection: BaseDBAsyncClient
) -> None:
    await VacancyCriterion.filter(vacancy_id=vacancy_id).using_db(connection).delete()
    if not criteria:
        return
    await VacancyCriterion.bulk_create(
        [
            VacancyCriterion(
                vacancy_id=vacancy_id,
                type=criterion.type,
                required=criterion.required,
                value=criterion.value,
                weight=criterion.weight,
            )
            for criterion in criteria
        ],
        using_db=connection,
    )


async def _replace_questions(
    vacancy_id: int,
    questions: list[ScreeningQuestionWrite],
    *,
    connection: BaseDBAsyncClient,
) -> None:
    await ScreeningQuestion.filter(vacancy_id=vacancy_id).using_db(connection).delete()
    if not questions:
        return
    await ScreeningQuestion.bulk_create(
        [
            ScreeningQuestion(
                vacancy_id=vacancy_id,
                question=question.question,
                type=question.type,
                required=question.required,
                # Порядок задаёт сам список, а не поле в теле запроса
                sort_order=order,
                validation_rules=question.validation_rules,
            )
            for order, question in enumerate(questions, start=1)
        ],
        using_db=connection,
    )


async def _new_public_token(connection: BaseDBAsyncClient) -> str:
    """Токен публичной ссылки `{APP_URL}/v/{public_token}` (раздел 15).

    Совпадение 192-битного токена практически невозможно, но колонка
    UNIQUE: лучше повторить генерацию, чем уронить публикацию.
    """
    for _ in range(PUBLIC_TOKEN_ATTEMPTS):
        token = secrets.token_urlsafe(PUBLIC_TOKEN_BYTES)
        taken = await (
            Vacancy.filter(public_token=token).using_db(connection).exists()
        )
        if not taken:
            return token
        logger.warning("Токен публичной ссылки совпал с существующим")
    raise ConflictError(
        "Не удалось выдать ссылку на вакансию", code="public_token_unavailable"
    )


async def vacancy_analytics(
    user: User,
    vacancy_id: int,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> VacancyAnalyticsResponse:
    """Сводка аналитики по вакансии (E18 UX-карты, функция 33, раздел 69
    тех-доки). Считается из уже существующих таблиц — отдельной модели нет.

    `invited` — по `employer_decisions`, не по `applications.status`: решение
    «пригласить» сразу переводит отклик в `mutual_interest` (раздел 36),
    `invited` как хранимое состояние не встречается (см. `decide()`).

    `time_to_first_interview_seconds` считается от создания вакансии (а не от
    публикации — отдельного поля даты публикации в модели нет) до первого
    назначенного собеседования; `None`, если собеседований ещё не было.
    Период (`date_from`/`date_to`) фильтрует каждую сущность по её `created_at`.
    """
    vacancy = await get_own_vacancy(user, vacancy_id)
    period = _period_filter(date_from, date_to)

    applications_total = await Application.filter(
        vacancy_id=vacancy.id, **period
    ).count()
    passed_hard_filters = await Application.filter(
        vacancy_id=vacancy.id, **period
    ).exclude(
        status__in=[
            ApplicationStatus.CREATED,
            ApplicationStatus.SCREENING,
            ApplicationStatus.HARD_FILTER_FAILED,
        ]
    ).count()
    invited = await EmployerDecision.filter(
        application__vacancy_id=vacancy.id, action=DecisionAction.INVITED, **period
    ).count()
    mutual_interest = await Match.filter(
        application__vacancy_id=vacancy.id, **period
    ).count()
    interviews = Interview.filter(match__application__vacancy_id=vacancy.id, **period)
    interviews_booked = await interviews.count()
    first_interview = await interviews.order_by("created_at").first()

    time_to_first_interview_seconds = (
        int((first_interview.created_at - vacancy.created_at).total_seconds())
        if first_interview is not None
        else None
    )

    return VacancyAnalyticsResponse(
        vacancy_id=vacancy.id,
        applications_total=applications_total,
        passed_hard_filters=passed_hard_filters,
        invited=invited,
        mutual_interest=mutual_interest,
        interviews_booked=interviews_booked,
        time_to_first_interview_seconds=time_to_first_interview_seconds,
    )


def _period_filter(
    date_from: datetime | None, date_to: datetime | None
) -> dict[str, datetime]:
    period: dict[str, datetime] = {}
    if date_from is not None:
        period["created_at__gte"] = date_from
    if date_to is not None:
        period["created_at__lte"] = date_to
    return period


async def get_calibration_profiles(
    user: User, vacancy_id: int
) -> CalibrationProfilesResponse:
    """Синтетические тестовые карточки калибровки (E17 UX-карты, функция 25)."""
    vacancy = await get_own_vacancy(user, vacancy_id)
    criteria = await VacancyCriterion.filter(vacancy_id=vacancy.id)
    profiles = calibration.generate_test_profiles(criteria)
    return CalibrationProfilesResponse(
        profiles=[
            CalibrationProfileRead(
                pattern_token=profile.pattern_token,
                criteria=[
                    CalibrationCriterionRead(
                        type=item.type, matches=item.matches, value_label=item.value_label
                    )
                    for item in profile.criteria
                ],
            )
            for profile in profiles
        ]
    )


async def submit_calibration(
    user: User, vacancy_id: int, payload: CalibrationSubmitRequest
) -> CalibrationWeightsResponse:
    """Считает веса по решениям работодателя и обновляет их у критериев на
    месте (`UPDATE`, не `_replace_criteria`) — сами критерии и их `id` не
    меняются, только `weight`. Логирует `vacancy_calibration_completed`
    (раздел 60 тех-доки)."""
    vacancy = await get_own_vacancy(user, vacancy_id)
    criteria = await VacancyCriterion.filter(vacancy_id=vacancy.id)
    votes = {vote.pattern_token: vote.fit for vote in payload.votes}
    weights = calibration.compute_weights(criteria, votes)

    if weights:
        async with in_transaction() as connection:
            for criterion in criteria:
                if criterion.type not in weights:
                    continue
                criterion.weight = weights[criterion.type]
                await criterion.save(using_db=connection, update_fields=["weight"])

        await analytics.log_event(
            "vacancy_calibration_completed",
            user_id=user.user_id,
            payload={
                "vacancy_id": vacancy.id,
                "weights": {
                    criterion_type.value: str(weight)
                    for criterion_type, weight in weights.items()
                },
            },
        )
    return CalibrationWeightsResponse(weights=weights)


async def create_referral_link(user: User, vacancy_id: int) -> ReferralLinkRead:
    """Реферальная ссылка на вакансию (R01 UX-карты, функция 32, раздел 68
    тех-доки). Ссылка ведёт на уже существующий публичный маршрут вакансии
    (раздел 15) с добавленным источником — отдельный маршрут не заводим.

    Требует опубликованную вакансию: `public_token` появляется только при
    публикации, а рекомендовать черновик, который ещё никто не видит, нечем.
    """
    vacancy = await get_own_vacancy(user, vacancy_id)
    if vacancy.public_token is None:
        raise ConflictError(
            "У вакансии ещё нет публичной ссылки — сначала опубликуйте её",
            code="vacancy_not_published",
        )

    for _ in range(REFERRAL_CODE_ATTEMPTS):
        code = secrets.token_urlsafe(REFERRAL_CODE_BYTES)
        try:
            link = await ReferralLink.create(
                vacancy_id=vacancy.id, source_user_id=user.user_id, code=code
            )
        except IntegrityError:
            logger.warning("Код реферальной ссылки совпал с существующим")
            continue
        await analytics.log_event(
            "referral_link_created",
            user_id=user.user_id,
            payload={"vacancy_id": vacancy.id, "code": code},
        )
        return _referral_read(link, vacancy)
    raise ConflictError(
        "Не удалось создать реферальную ссылку", code="referral_code_unavailable"
    )


async def list_referral_links(user: User, vacancy_id: int) -> ReferralLinkListResponse:
    """Уже созданные реферальные ссылки вакансии. Не из тех-доки — естественное
    дополнение к созданию (`POST`), как и списки вакансий/слотов в остальном API."""
    vacancy = await get_own_vacancy(user, vacancy_id)
    links = await ReferralLink.filter(vacancy_id=vacancy.id).order_by("-created_at")
    return ReferralLinkListResponse(
        items=[_referral_read(link, vacancy) for link in links]
    )


def _referral_read(link: ReferralLink, vacancy: Vacancy) -> ReferralLinkRead:
    url = _public_url(vacancy)
    return ReferralLinkRead(
        code=link.code,
        url=f"{url}?ref={link.code}" if url else "",
        created_at=link.created_at,
    )


async def _read(
    vacancy: Vacancy, *, owner: bool, background_tasks: BackgroundTasks | None = None
) -> VacancyRead:
    return (
        await _read_many([vacancy], owner=owner, background_tasks=background_tasks)
    )[0]


async def _read_many(
    vacancies: list[Vacancy],
    *,
    owner: bool,
    background_tasks: BackgroundTasks | None = None,
) -> list[VacancyRead]:
    """Собирает ответы страницы: число запросов не зависит от её размера.

    `background_tasks`: только для отдачи одной вакансии (`GET /vacancies/{id}`
    и её эквиваленты). Ответ уходит с той ссылкой на фото, что уже сохранена —
    подбор недостающей (`images.ensure_fresh_image`) идёт в фоне, после ответа:
    внешний Openverse не должен быть обязательной частью пути P0 (раздел 83).
    Уже назначенное фото фоновая задача не меняет — следующее открытие
    карточки увидит либо то же фото, либо впервые найденное, если раньше
    подбор не удался. В списках (лента, кабинет работодателя) фоновая задача
    не планируется вовсе — иначе один список запускал бы до `limit` фоновых
    запросов разом.
    """
    if not vacancies:
        return []

    if background_tasks is not None:
        for vacancy in vacancies:
            background_tasks.add_task(images.ensure_fresh_image, vacancy)

    vacancy_ids = [vacancy.id for vacancy in vacancies]
    criteria: dict[int, list[VacancyCriterion]] = {}
    for criterion in await VacancyCriterion.filter(
        vacancy_id__in=vacancy_ids
    ).order_by("id"):
        criteria.setdefault(criterion.vacancy_id, []).append(criterion)

    questions: dict[int, list[ScreeningQuestion]] = {}
    for question in await ScreeningQuestion.filter(
        vacancy_id__in=vacancy_ids
    ).order_by("sort_order", "id"):
        questions.setdefault(question.vacancy_id, []).append(question)

    counts: dict[int, int] = {}
    if owner:
        rows = (
            await Application.filter(vacancy_id__in=vacancy_ids)
            .annotate(total=Count("id"))
            .group_by("vacancy_id")
            .values("vacancy_id", "total")
        )
        counts = {row["vacancy_id"]: row["total"] for row in rows}

    return [
        _build_read(
            vacancy,
            criteria.get(vacancy.id, []),
            questions.get(vacancy.id, []),
            owner=owner,
            applications_count=counts.get(vacancy.id, 0) if owner else None,
        )
        for vacancy in vacancies
    ]


def _build_read(
    vacancy: Vacancy,
    criteria: list[VacancyCriterion],
    questions: list[ScreeningQuestion],
    *,
    owner: bool,
    applications_count: int | None,
) -> VacancyRead:
    return VacancyRead(
        id=vacancy.id,
        employer_id=vacancy.employer_id,
        title=vacancy.title,
        company_name=vacancy.company_name,
        description=vacancy.description,
        location=vacancy.location,
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        schedule=vacancy.schedule,
        image_url=vacancy.image_url,
        status=vacancy.status,
        public_token=vacancy.public_token if owner else None,
        public_url=_public_url(vacancy) if owner else None,
        applications_count=applications_count,
        criteria=[
            CriterionRead(
                id=criterion.id,
                type=criterion.type,
                required=criterion.required,
                value=criterion.value,
                weight=criterion.weight,
            )
            for criterion in criteria
        ],
        questions=[
            ScreeningQuestionRead(
                id=question.id,
                question=question.question,
                type=question.type,
                required=question.required,
                sort_order=question.sort_order,
                # Отсекающее условие видит только владелец вакансии: зная
                # его, кандидат просто подогнал бы ответ
                validation_rules=(
                    _rules(question) if owner else public_rules(question)
                ),
            )
            for question in questions
        ],
        created_at=vacancy.created_at,
        updated_at=vacancy.updated_at,
    )


def _rules(question: ScreeningQuestion) -> dict[str, Any] | None:
    rules = question.validation_rules
    return rules if isinstance(rules, dict) else None


def _public_url(vacancy: Vacancy) -> str | None:
    """Ссылка вида `{APP_URL}/v/{public_token}` (раздел 15)."""
    if vacancy.public_token is None:
        return None
    return f"{settings.app_url.rstrip('/')}/v/{vacancy.public_token}"
