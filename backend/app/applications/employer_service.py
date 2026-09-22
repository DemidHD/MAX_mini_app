"""Работа работодателя с откликами: список кандидатов и решение.

Разделы 20, 26, 34, 35, 56 тех-доки. Кандидатская часть отклика (первичный
отбор) живёт в `service.py` — разделены по тому, чья это сторона сценария.

Права всегда проверяются через вакансию: отклик доступен работодателю только
тогда, когда вакансия принадлежит пользователю из сессии. Идентификаторы из
тела запроса источником истины не являются.
"""

import logging

from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import Application, EmployerDecision, ScreeningAnswer
from app.applications.schemas import (
    CandidateCard,
    CandidateListResponse,
    CardCriterionResult,
    CardScreeningAnswer,
    DecisionRequest,
    DecisionResponse,
)
from app.applications.screening import stored_value
from app.applications.state import ensure_transition
from app.candidates.models import CandidateProfile
from app.core.database import utcnow
from app.core.enums import ApplicationStatus, DecisionAction
from app.core.errors import NotFoundError, ValidationError
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy

logger = logging.getLogger("app.applications.employer")

# В список работодателя попадают отклики, прошедшие первичный отбор. Те, кто
# его не проходил или не прошёл, работодателю не показываются: обязательная
# фильтрация на то и нужна, чтобы он их не разбирал (функция 8 ТЗ).
REVIEWABLE_STATUSES = (
    ApplicationStatus.PASSED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.INVITED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.MUTUAL_INTEREST,
    ApplicationStatus.INTERVIEW_SCHEDULED,
    ApplicationStatus.INTERVIEW_COMPLETED,
)

# Решение работодателя переводит отклик в этот статус
DECISION_TARGET = {
    DecisionAction.INVITED: ApplicationStatus.INVITED,
    DecisionAction.REJECTED: ApplicationStatus.REJECTED,
}


async def list_candidates(
    user: User, vacancy_id: int, *, limit: int, offset: int
) -> CandidateListResponse:
    """Кандидаты вакансии, прошедшие первичный отбор (разделы 27, 34).

    Карточка собирается одинаково для всех кандидатов и содержит только
    рабочие факторы: ни имени, ни фото раздел 34 в ней не предусматривает.

    Результат обязательных фильтров берётся из снимка, сделанного на отборе,
    а не считается заново: кандидат прошёл отбор — работодатель видит именно
    то соответствие, по которому отклик был допущен. Изменение профиля после
    отбора карточку не переписывает.
    """
    vacancy = await _own_vacancy(user, vacancy_id)

    applications_query = Application.filter(
        vacancy_id=vacancy.id, status__in=REVIEWABLE_STATUSES
    )
    total = await applications_query.count()
    # `-id` вторым ключом: у откликов, созданных в одну миллисекунду, порядок
    # иначе не определён, и страницы могли бы перекрываться
    applications = await (
        applications_query.order_by("-created_at", "-id").offset(offset).limit(limit)
    )

    return CandidateListResponse(
        items=await _build_cards(vacancy, applications),
        limit=limit,
        offset=offset,
        total=total,
    )


async def decide(
    user: User, application_id: int, payload: DecisionRequest
) -> DecisionResponse:
    """Решение работодателя по отклику (раздел 35).

    Раздел 56 требует выполнять решение и смену статуса одной транзакцией.
    Отклик блокируется, а переход перепроверяется под блокировкой: два
    одновременных нажатия не должны дать два решения.

    Уведомление `candidate_invited` (раздел 46) отправляется после commit и
    подключается на этапе 7 — ошибка уведомления не отменяет решение.
    """
    action = _ensure_supported_action(payload)
    target = DECISION_TARGET[action]
    application = await _own_application(user, application_id)
    ensure_transition(application.status, target)

    decided_at = utcnow()
    async with in_transaction() as connection:
        locked = await (
            Application.filter(id=application.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        ensure_transition(locked.status, target)

        await EmployerDecision.create(
            application_id=locked.id,
            action=action,
            reject_reason=payload.reject_reason,
            using_db=connection,
        )
        locked.status = target
        await locked.save(using_db=connection, update_fields=["status", "updated_at"])

    await analytics.log_event(
        "candidate_invited"
        if action is DecisionAction.INVITED
        else "candidate_rejected",
        user_id=user.user_id,
        payload={
            "application_id": application.id,
            "vacancy_id": application.vacancy_id,
            "reject_reason": (
                payload.reject_reason.value if payload.reject_reason else None
            ),
        },
    )
    logger.info(
        "Решение работодателя: отклик=%s действие=%s", application.id, action.value
    )

    return DecisionResponse(
        application_id=application.id,
        status=target,
        action=action,
        reject_reason=payload.reject_reason,
        decided_at=decided_at,
    )


def _ensure_supported_action(payload: DecisionRequest) -> DecisionAction:
    """Раздел 20: в P0 backend принимает только `rejected` и `invited`."""
    if payload.action is DecisionAction.RESERVED:
        raise ValidationError(
            "Перевод в резерв относится к P1 и пока недоступен",
            code="decision_action_not_supported",
            details={"action": payload.action.value},
        )
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
    """Вакансия текущего работодателя.

    Чужая вакансия — `404`, а не `403`: существование чужих вакансий наружу
    не раскрывается.
    """
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None or vacancy.employer_id != user.user_id:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    return vacancy


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
    vacancy: Vacancy, applications: list[Application]
) -> list[CandidateCard]:
    """Собирает карточки страницы.

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
        )
        for application in applications
    ]


def _build_card(
    application: Application,
    profile: CandidateProfile | None,
    answers: list[ScreeningAnswer],
    questions: dict[int, ScreeningQuestion],
) -> CandidateCard:
    return CandidateCard(
        application_id=application.id,
        status=application.status,
        applied_at=application.created_at,
        desired_role=profile.desired_role if profile else None,
        city=profile.city if profile else None,
        salary=profile.salary if profile else None,
        schedule=profile.schedule if profile else None,
        experience_months=profile.experience_months if profile else None,
        available_from=profile.available_from if profile else None,
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
        hard_filters=_hard_filters(application),
    )


def _hard_filters(application: Application) -> list[CardCriterionResult]:
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
        CardCriterionResult(
            type=item["type"], required=item["required"], passed=item["passed"]
        )
        for item in criteria
        if isinstance(item, dict)
    ]
