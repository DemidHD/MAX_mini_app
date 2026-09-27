"""Работа работодателя с откликами: список кандидатов и решение.

Разделы 20, 26, 34, 35, 36, 56 тех-доки. Кандидатская часть отклика (первичный
отбор) живёт в `service.py` — разделены по тому, чья это сторона сценария.

Права всегда проверяются через вакансию: отклик доступен работодателю только
тогда, когда вакансия принадлежит пользователю из сессии. Идентификаторы из
тела запроса источником истины не являются.
"""

import logging
from decimal import Decimal

from fastapi import BackgroundTasks
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import (
    Application,
    EmployerDecision,
    Match,
    ScreeningAnswer,
)
from app.applications.schemas import (
    CandidateCard,
    CandidateListResponse,
    CardCriterionResult,
    CardScreeningAnswer,
    DecisionRequest,
    DecisionResponse,
    ExperienceExplanation,
    MatchExplanation,
)
from app.applications.screening import stored_value
from app.applications.state import ensure_transition
from app.candidates.models import CandidateProfile
from app.core.database import utcnow
from app.core.enums import ApplicationStatus, CriterionType, DecisionAction
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.matching.explain import explain as build_explanation
from app.matching.learning import learned_weight_adjustment
from app.matching.ranking import CriterionOutcome, rank as rank_criteria
from app.matching.rules import (
    evaluate_vacancy,
    matches_required_criteria,
    months_from_criterion_value,
)
from app.notifications.service import notification_service
from app.skills.service import resolve_skill_names, skills_for_profile
from app.users.models import User
from app.vacancies import service as vacancies_service
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion

logger = logging.getLogger("app.applications.employer")

# В список работодателя попадают отклики, прошедшие первичный отбор. Те, кто
# его не проходил или не прошёл, работодателю не показываются: обязательная
# фильтрация на то и нужна, чтобы он их не разбирал (функция 8 ТЗ).
REVIEWABLE_STATUSES = (
    ApplicationStatus.PASSED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.RESERVED,
    ApplicationStatus.INVITED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.MUTUAL_INTEREST,
    ApplicationStatus.INTERVIEW_SCHEDULED,
    ApplicationStatus.INTERVIEW_COMPLETED,
)

# Статус, который выставляет само решение работодателя. Для приглашения это
# не конечный статус операции: следом создаётся match (раздел 36), и отклик
# уходит в `mutual_interest` — см. `_create_match`.
DECISION_TARGET = {
    DecisionAction.INVITED: ApplicationStatus.INVITED,
    DecisionAction.REJECTED: ApplicationStatus.REJECTED,
    DecisionAction.RESERVED: ApplicationStatus.RESERVED,
}

# Аналитическое имя события по действию работодателя (раздел 60)
_DECISION_EVENT_NAME = {
    DecisionAction.INVITED: "candidate_invited",
    DecisionAction.REJECTED: "candidate_rejected",
    DecisionAction.RESERVED: "candidate_reserved",
}


async def list_candidates(
    user: User, vacancy_id: int, *, limit: int, offset: int
) -> CandidateListResponse:
    """Кандидаты вакансии, прошедшие первичный отбор (разделы 27, 34, 65).

    Карточка собирается одинаково для всех кандидатов и содержит только
    рабочие факторы: ни имени, ни фото раздел 34 в ней не предусматривает.

    Результат обязательных фильтров берётся из снимка, сделанного на отборе,
    а не считается заново: кандидат прошёл отбор — работодатель видит именно
    то соответствие, по которому отклик был допущен. Изменение профиля после
    отбора карточку не переписывает.

    Список сортируется ранжированием (раздел 65): сначала кандидаты с большим
    весом совпавших желательных критериев, при равенстве — как раньше, от
    новых откликов к старым. Страница вакансии на масштабе микробизнеса
    небольшая, поэтому сортировка и пагинация выполняются в Python по всей
    выборке — так же, как в ленте (`app.matching.service.get_feed`), а не на
    уровне SQL, которому нечем посчитать вес критерия.
    """
    vacancy = await _own_vacancy(user, vacancy_id)

    # `-id` вторым ключом: у откликов, созданных в одну миллисекунду, порядок
    # иначе не определён, и страницы могли бы перекрываться. `sorted` ниже
    # стабильна, поэтому этот порядок остаётся тай-брейком внутри ranking.
    applications = await Application.filter(
        vacancy_id=vacancy.id, status__in=REVIEWABLE_STATUSES
    ).order_by("-created_at", "-id")
    total = len(applications)

    weights, experience_required = await _criteria_context(vacancy.id, user.user_id)
    ranked = sorted(
        await _build_cards(
            vacancy,
            applications,
            weights=weights,
            experience_required=experience_required,
        ),
        key=lambda scored: scored[1],
        reverse=True,
    )

    return CandidateListResponse(
        items=[card for card, _score in ranked[offset : offset + limit]],
        limit=limit,
        offset=offset,
        total=total,
    )


async def list_reserved_candidates(
    user: User, vacancy_id: int, *, limit: int, offset: int
) -> CandidateListResponse:
    """Кандидаты из резерва по другим вакансиям, подходящие этой (функция 30
    UX-карты, E16 в режиме P2): «При новой вакансии сначала показать прошлых
    подходящих кандидатов». Новой таблицы нет — резерв уже есть в
    `applications.status=reserved` (P1, функция 22, `decision.action=reserve`).

    Кандидат из резерва проверяется по условиям ИМЕННО этой вакансии заново
    (`app.matching.rules.evaluate_vacancy`, та же функция, что и в ленте) —
    снимок первичного отбора здесь не годится, он снят на другой вакансии с
    другими критериями. Кто не проходит обязательные условия — не попадает
    в список, как и в обычном списке кандидатов.

    Один кандидат мог попасть в резерв с нескольких вакансий — берётся
    последнее по времени решение о резерве.
    """
    vacancy = await _own_vacancy(user, vacancy_id)
    weights, experience_required = await _criteria_context(vacancy.id, user.user_id)
    criteria = await VacancyCriterion.filter(vacancy_id=vacancy.id)

    reserved = (
        await Application.filter(
            status=ApplicationStatus.RESERVED, vacancy__employer_id=user.user_id
        )
        .exclude(vacancy_id=vacancy.id)
        .order_by("-updated_at", "-id")
    )
    latest_by_candidate: dict[int, Application] = {}
    for application in reserved:
        latest_by_candidate.setdefault(application.candidate_id, application)

    profiles = {
        profile.user_id: profile
        for profile in await CandidateProfile.filter(
            user_id__in=list(latest_by_candidate.keys())
        )
    }
    skill_names = await resolve_skill_names(
        skill_id
        for profile in profiles.values()
        for skill_id in profile.skill_ids or []
    )

    scored: list[tuple[CandidateCard, Decimal]] = []
    for candidate_id, application in latest_by_candidate.items():
        profile = profiles.get(candidate_id)
        results = evaluate_vacancy(vacancy, criteria, profile)
        if not matches_required_criteria(results):
            continue
        outcomes = [
            CriterionOutcome(type=result.type, required=result.required, passed=result.passed)
            for result in results
        ]
        scored.append(
            _build_reserved_card(
                application,
                profile,
                outcomes,
                weights=weights,
                experience_required=experience_required,
                skill_names=skill_names,
            )
        )

    scored.sort(key=lambda scored_card: scored_card[1], reverse=True)
    total = len(scored)
    return CandidateListResponse(
        items=[card for card, _score in scored[offset : offset + limit]],
        limit=limit,
        offset=offset,
        total=total,
    )


def _build_reserved_card(
    application: Application,
    profile: CandidateProfile | None,
    outcomes: list[CriterionOutcome],
    *,
    weights: dict[CriterionType, Decimal],
    experience_required: int | None,
    skill_names: dict[int, str],
) -> tuple[CandidateCard, Decimal]:
    ranking = rank_criteria(outcomes, weights)
    explanation = build_explanation(
        outcomes,
        experience_required_months=experience_required,
        candidate_experience_months=profile.experience_months if profile else None,
    )
    card = CandidateCard(
        application_id=application.id,
        status=application.status,
        applied_at=application.created_at,
        desired_role=profile.desired_role if profile else None,
        city=profile.city if profile else None,
        salary=profile.salary if profile else None,
        schedule=profile.schedule if profile else None,
        experience_months=profile.experience_months if profile else None,
        available_from=profile.available_from if profile else None,
        skills=skills_for_profile(profile, skill_names),
        # Резервный кандидат пришёл с другой вакансии — её вопросы отбора к
        # этой не относятся, показывать их здесь нечем.
        screening_answers=[],
        hard_filters=[
            CardCriterionResult(
                type=outcome.type, required=outcome.required, passed=outcome.passed
            )
            for outcome in outcomes
        ],
        explanation=MatchExplanation(
            matched=explanation.matched,
            experience=(
                ExperienceExplanation(
                    candidate=explanation.experience.candidate,
                    required=explanation.experience.required,
                )
                if explanation.experience
                else None
            ),
        ),
    )
    return card, ranking.score


async def _criteria_context(
    vacancy_id: int, employer_id: int
) -> tuple[dict[CriterionType, Decimal], int | None]:
    """Веса критериев и требуемый опыт (в месяцах) для ranking и объяснимости.

    Берутся из текущих критериев вакансии, а не из снимка отбора: раздел 65
    только сортирует список и не меняет статус кандидата, поэтому нужны
    актуальные веса работодателя, а не те, что были на момент отбора.
    Двух критериев одного типа контракт не запрещает — берётся первый.

    Функция 30 UX-карты (E07, режим P2 «Персонализированная очередь»):
    критерию без явного веса (ни калибровки, ни ручного значения) подставляется
    поправка, посчитанная по истории решений работодателя — `app.matching.learning`.
    Явный вес работодателя поправка не трогает.
    """
    weights: dict[CriterionType, Decimal] = {}
    experience_required: int | None = None
    desirable_types: set[CriterionType] = set()
    for criterion in await VacancyCriterion.filter(vacancy_id=vacancy_id):
        if criterion.type not in weights and criterion.weight is not None:
            weights[criterion.type] = criterion.weight
        if criterion.type is CriterionType.EXPERIENCE and experience_required is None:
            value = criterion.value if isinstance(criterion.value, dict) else {}
            experience_required = months_from_criterion_value(value.get("min_months"))
        if not criterion.required:
            desirable_types.add(criterion.type)

    missing = desirable_types - weights.keys()
    if missing:
        learned = await learned_weight_adjustment(employer_id)
        for criterion_type in missing:
            if criterion_type in learned:
                weights[criterion_type] = learned[criterion_type]
    return weights, experience_required


async def decide(
    user: User,
    application_id: int,
    payload: DecisionRequest,
    background_tasks: BackgroundTasks,
) -> DecisionResponse:
    """Решение работодателя по отклику (разделы 20, 35, 36).

    Раздел 56 требует выполнять решение и смену статуса одной транзакцией.
    Отклик блокируется, а переход перепроверяется под блокировкой: два
    одновременных нажатия не должны дать два решения.

    Приглашение выполняется целиком здесь же: решение, match и перевод в
    `mutual_interest` — одна операция, иначе отклик мог бы остаться в
    `invited` без match, и кандидату нечего было бы бронировать.

    `reserved` (функция «Резерв», P1) — тоже промежуточное решение: из него
    работодатель может позже пригласить или отклонить тем же эндпоинтом
    (переход описан в `state.py`).

    Уведомления (раздел 46) планируются в фоне, после commit: ошибка
    уведомления решение не отменяет (раздел 47), а повторы отправки не должны
    держать работодателя перед экраном решения.
    """
    action = _ensure_supported_action(payload)
    decision_status = DECISION_TARGET[action]
    application = await _own_application(user, application_id)
    ensure_transition(application.status, decision_status)

    decided_at = utcnow()
    final_status = decision_status
    match_id: int | None = None
    async with in_transaction() as connection:
        locked = await (
            Application.filter(id=application.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        ensure_transition(locked.status, decision_status)

        await EmployerDecision.create(
            application_id=locked.id,
            action=action,
            reject_reason=payload.reject_reason,
            using_db=connection,
        )
        if action is DecisionAction.INVITED:
            match_id = await _create_match(locked, connection=connection)
            final_status = ApplicationStatus.MUTUAL_INTEREST

        locked.status = final_status
        await locked.save(using_db=connection, update_fields=["status", "updated_at"])

    await analytics.log_event(
        _DECISION_EVENT_NAME[action],
        user_id=user.user_id,
        payload={
            "application_id": application.id,
            "vacancy_id": application.vacancy_id,
            "reject_reason": (
                payload.reject_reason.value if payload.reject_reason else None
            ),
        },
    )
    if match_id is not None:
        await analytics.log_event(
            "match_created",
            user_id=user.user_id,
            payload={
                "match_id": match_id,
                "application_id": application.id,
                "vacancy_id": application.vacancy_id,
            },
        )
    if match_id is not None:
        await _notify_invited(user, application, match_id, background_tasks)
    elif action is DecisionAction.RESERVED:
        await _notify_reserved(application, background_tasks)
    elif action is DecisionAction.REJECTED:
        await _notify_rejected(application, background_tasks)
    logger.info(
        "Решение работодателя: отклик=%s действие=%s статус=%s",
        application.id,
        action.value,
        final_status.value,
    )

    return DecisionResponse(
        application_id=application.id,
        status=final_status,
        action=action,
        reject_reason=payload.reject_reason,
        match_id=match_id,
        decided_at=decided_at,
    )


async def _notify_invited(
    user: User,
    application: Application,
    match_id: int,
    background_tasks: BackgroundTasks,
) -> None:
    """Уведомления приглашённому кандидату и обеим сторонам (раздел 46).

    Название вакансии читается уже после commit: в тексте сообщения оно
    нужно, а держать лишние данные в транзакции незачем. Сама отправка
    (`maxapi`, с повторами) планируется в фоне — она не должна держать
    работодателя перед ответом на решение.
    """
    vacancy = await Vacancy.get_or_none(id=application.vacancy_id)
    if vacancy is None:
        # FK с каскадом: отклика без вакансии не бывает
        logger.warning("Вакансия отклика %s не найдена", application.id)
        return

    background_tasks.add_task(
        notification_service.candidate_invited,
        candidate_id=application.candidate_id,
        application_id=application.id,
        vacancy_title=vacancy.title,
    )
    background_tasks.add_task(
        notification_service.mutual_interest,
        match_id=match_id,
        application_id=application.id,
        candidate_id=application.candidate_id,
        employer_id=user.user_id,
        vacancy_title=vacancy.title,
    )


async def _notify_reserved(
    application: Application, background_tasks: BackgroundTasks
) -> None:
    """Уведомление кандидату о переводе в резерв (P1, раздел 46)."""
    vacancy = await Vacancy.get_or_none(id=application.vacancy_id)
    if vacancy is None:
        logger.warning("Вакансия отклика %s не найдена", application.id)
        return

    background_tasks.add_task(
        notification_service.application_reserved,
        candidate_id=application.candidate_id,
        application_id=application.id,
        vacancy_title=vacancy.title,
    )


async def _notify_rejected(
    application: Application, background_tasks: BackgroundTasks
) -> None:
    """Уведомление кандидату об отказе (функции 27-28 UX-карты, раздел 46)."""
    vacancy = await Vacancy.get_or_none(id=application.vacancy_id)
    if vacancy is None:
        logger.warning("Вакансия отклика %s не найдена", application.id)
        return

    background_tasks.add_task(
        notification_service.application_rejected,
        candidate_id=application.candidate_id,
        application_id=application.id,
        vacancy_title=vacancy.title,
    )


async def _create_match(
    application: Application, *, connection: BaseDBAsyncClient
) -> int:
    """Создаёт взаимный интерес по приглашению (раздел 36).

    Приглашение и есть взаимный интерес: кандидат выразил его откликом,
    последнее слово остаётся за работодателем, и отдельного подтверждения
    кандидата сценарий не предусматривает. Поэтому `invited` — переходное
    состояние внутри одной операции (карта переходов в `state.py`).

    Переход проверяется через ту же карту, что и остальные: если ветка
    `invited → mutual_interest` из неё исчезнет, приглашение должно
    сломаться здесь, а не молча разойтись с разделом 26.
    """
    ensure_transition(ApplicationStatus.INVITED, ApplicationStatus.MUTUAL_INTEREST)

    # `matches.application_id` UNIQUE (раздел 55), и match создаётся только
    # здесь, под блокировкой отклика в статусе `passed`/`under_review`.
    # Уже существующий match означает расхождение данных, а не гонку.
    exists = await (
        Match.filter(application_id=application.id).using_db(connection).exists()
    )
    if exists:
        logger.warning(
            "У отклика %s уже есть match, хотя статус — %s",
            application.id,
            application.status.value,
        )
        raise ConflictError(
            "По этому отклику уже есть взаимный интерес",
            code="match_already_exists",
            details={"application_id": application.id},
        )

    match = await Match.create(application_id=application.id, using_db=connection)
    logger.info("Создан match %s по отклику %s", match.id, application.id)
    return match.id


def _ensure_supported_action(payload: DecisionRequest) -> DecisionAction:
    """Раздел 20: причина отказа осмысленна только вместе с `rejected`."""
    if payload.reject_reason is not None and payload.action is not (
        DecisionAction.REJECTED
    ):
        # Причина отказа без отказа — почти наверняка ошибка формы
        raise ValidationError(
            "Причина отказа допустима только вместе с отклонением",
            code="reject_reason_not_applicable",
            details={"action": payload.action.value},
        )
    return payload.action


async def _own_vacancy(user: User, vacancy_id: int) -> Vacancy:
    """Вакансия текущего работодателя. Проверка общая со слотами."""
    return await vacancies_service.get_own_vacancy(user, vacancy_id)


async def _own_application(user: User, application_id: int) -> Application:
    """Отклик на вакансию текущего работодателя."""
    application = await Application.get_or_none(id=application_id)
    if application is None:
        raise NotFoundError("Отклик не найден", code="application_not_found")

    vacancy = await Vacancy.get_or_none(id=application.vacancy_id)
    if vacancy is None or vacancy.employer_id != user.user_id:
        raise NotFoundError("Отклик не найден", code="application_not_found")
    return application


async def _build_cards(
    vacancy: Vacancy,
    applications: list[Application],
    *,
    weights: dict[CriterionType, Decimal],
    experience_required: int | None,
) -> list[tuple[CandidateCard, Decimal]]:
    """Собирает карточки страницы вместе с ключом ранжирования каждой.

    Число запросов не зависит от размера страницы: профили, ответы и вопросы
    читаются пакетами, критерии и вопросы общие для всей вакансии.
    """
    if not applications:
        return []

    application_ids = [application.id for application in applications]
    candidate_ids = [application.candidate_id for application in applications]

    questions = {
        question.id: question
        for question in await ScreeningQuestion.filter(vacancy_id=vacancy.id)
    }
    profiles = {
        profile.user_id: profile
        for profile in await CandidateProfile.filter(user_id__in=candidate_ids)
    }
    skill_names = await resolve_skill_names(
        skill_id
        for profile in profiles.values()
        for skill_id in profile.skill_ids or []
    )
    answers: dict[int, list[ScreeningAnswer]] = {}
    for answer in await ScreeningAnswer.filter(
        application_id__in=application_ids
    ).order_by("question_id"):
        answers.setdefault(answer.application_id, []).append(answer)

    return [
        _build_card(
            application,
            profiles.get(application.candidate_id),
            answers.get(application.id, []),
            questions,
            weights=weights,
            experience_required=experience_required,
            skill_names=skill_names,
        )
        for application in applications
    ]


def _build_card(
    application: Application,
    profile: CandidateProfile | None,
    answers: list[ScreeningAnswer],
    questions: dict[int, ScreeningQuestion],
    *,
    weights: dict[CriterionType, Decimal],
    experience_required: int | None,
    skill_names: dict[int, str],
) -> tuple[CandidateCard, Decimal]:
    outcomes = _criteria_outcomes(application)
    ranking = rank_criteria(outcomes, weights)
    explanation = build_explanation(
        outcomes,
        experience_required_months=experience_required,
        candidate_experience_months=profile.experience_months if profile else None,
    )

    card = CandidateCard(
        application_id=application.id,
        status=application.status,
        applied_at=application.created_at,
        desired_role=profile.desired_role if profile else None,
        city=profile.city if profile else None,
        salary=profile.salary if profile else None,
        schedule=profile.schedule if profile else None,
        experience_months=profile.experience_months if profile else None,
        available_from=profile.available_from if profile else None,
        skills=skills_for_profile(profile, skill_names),
        screening_answers=[
            CardScreeningAnswer(
                question_id=answer.question_id,
                question=questions[answer.question_id].question,
                type=questions[answer.question_id].type,
                value=stored_value(answer.value),
            )
            for answer in answers
            if answer.question_id in questions
        ],
        hard_filters=[
            CardCriterionResult(
                type=item.type, required=item.required, passed=item.passed
            )
            for item in outcomes
        ],
        explanation=MatchExplanation(
            matched=explanation.matched,
            experience=(
                ExperienceExplanation(
                    candidate=explanation.experience.candidate,
                    required=explanation.experience.required,
                )
                if explanation.experience
                else None
            ),
        ),
    )
    return card, ranking.score


def _criteria_outcomes(application: Application) -> list[CriterionOutcome]:
    """Снимок обязательных фильтров, сделанный на первичном отборе.

    Снимка нет только у отклика, не проходившего отбор в текущей версии кода;
    в список работодателя такой попасть не должен, поэтому пустой результат
    здесь — сигнал о расхождении данных, а не нормальный случай.
    """
    snapshot = application.hard_filter_result
    if not isinstance(snapshot, dict):
        logger.warning(
            "У отклика %s нет снимка обязательных фильтров", application.id
        )
        return []

    criteria = snapshot.get("criteria")
    if not isinstance(criteria, list):
        return []
    return [
        CriterionOutcome(
            type=CriterionType(item["type"]),
            required=item["required"],
            passed=item["passed"],
        )
        for item in criteria
        if isinstance(item, dict)
    ]
