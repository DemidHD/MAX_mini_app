"""Первичный отбор по отклику. Разделы 26, 33, 59 тех-доки.

Порядок работы backend задан разделом 33: проверить владельца отклика,
получить вопросы, проверить ответы, сохранить их, выполнить hard filters и
установить Passed/Failed.

Hard filters складываются из двух источников (раздел 59):

- обязательные критерии вакансии, проверяемые по профилю кандидата, —
  те же правила, что и в ленте (`app.matching.rules`);
- отсекающие условия на ответах первичного отбора — так в P0 проверяется
  обязательный `certificate`, которого нет в профиле.

Статусы меняет только backend (раздел 26): `created`/`screening` →
`passed` либо `hard_filter_failed`. Перевод в `under_review` относится к
работе работодателя и выполняется на этапе карточки кандидата.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import Application, Match, ScreeningAnswer
from app.applications.schemas import (
    CandidateApplicationListItem,
    CandidateApplicationListResponse,
    CandidateApplicationRead,
    ScreeningAnswerRead,
    ScreeningQuestionRead,
    ScreeningResultResponse,
    ScreeningStateResponse,
    ScreeningSubmitRequest,
)
from app.applications.screening import (
    AnswerCheck,
    check_answers,
    public_rules,
    stored_value,
)
from app.applications.state import SCREENING_SOURCE_STATUSES
from app.candidates.models import CandidateProfile
from app.core.enums import ApplicationStatus, CriterionType, VacancyStatus
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.interviews.models import Interview
from app.matching.rules import CriterionResult, evaluate_vacancy
from app.notifications.service import notification_service
from app.users.models import User
from app.vacancies import service as vacancies_service
from app.vacancies.models import ReferralLink, ScreeningQuestion, Vacancy, VacancyCriterion

logger = logging.getLogger("app.applications")



async def apply(
    user: User,
    vacancy_id: int,
    background_tasks: BackgroundTasks,
    referral_code: str | None = None,
) -> tuple[Application, bool]:
    """Отклик кандидата на вакансию (раздел 32).

    Проверки в порядке раздела 32: вакансия существует, вакансия
    опубликована, отклик ещё не создан. Роль и личность кандидата уже
    проверены зависимостью — идентификаторы из тела запроса не принимаются.

    Повторный отклик возвращает существующий, а не ошибку (раздел 57), и
    ничего не создаёт (раздел 79). Отдельная транзакция не нужна:
    единственность обеспечивает `UNIQUE(vacancy_id, candidate_id)`, и
    параллельный запрос ловится через `IntegrityError`.

    Уведомление `application_created` работодателю (раздел 46) отправляется
    в фоне, после ответа: ошибка отправки отклик не отменяет (раздел 47), а
    сама отправка — с повторами до `notification_retry_delay_seconds *
    attempt` — не должна держать кандидата перед экраном отбора.

    Возвращает отклик и признак того, что он создан именно этим запросом.
    """
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None:
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")
    if vacancy.status is not VacancyStatus.PUBLISHED:
        # Раздел 57: на закрытую вакансию новые отклики запрещены
        raise ConflictError(
            "Вакансия не принимает отклики",
            code="vacancy_not_published",
            details={"status": vacancy.status.value},
        )

    existing = await _existing_application(vacancy.id, user.user_id)
    if existing is not None:
        return existing, False

    # Функция 32 UX-карты (R01): источник отклика, если он пришёл по
    # реферальной ссылке. Неверный/чужой код не блокирует отклик — просто
    # не засчитывается, тем же принципом best-effort, что и подбор фото
    # вакансии (раздел 57).
    referral_link_id: int | None = None
    if referral_code:
        referral_link_id = await ReferralLink.filter(
            vacancy_id=vacancy.id, code=referral_code
        ).values_list("id", flat=True)
        referral_link_id = referral_link_id[0] if referral_link_id else None

    try:
        application = await Application.create(
            vacancy_id=vacancy.id,
            candidate_id=user.user_id,
            referral_link_id=referral_link_id,
            # Раздел 32: сразу после создания отклик идёт на первичный отбор
            status=ApplicationStatus.SCREENING,
        )
    except IntegrityError:
        logger.info("Отклик уже создан параллельным запросом")
        existing = await _existing_application(vacancy.id, user.user_id)
        if existing is None:
            raise
        return existing, False

    await analytics.log_event(
        "application_created",
        user_id=user.user_id,
        payload={"application_id": application.id, "vacancy_id": vacancy.id},
    )
    background_tasks.add_task(
        notification_service.application_created,
        employer_id=vacancy.employer_id,
        application_id=application.id,
        vacancy_title=vacancy.title,
    )
    logger.info("Создан отклик %s на вакансию %s", application.id, vacancy.id)
    return application, True


async def _existing_application(
    vacancy_id: int, candidate_id: int
) -> Application | None:
    return await Application.get_or_none(
        vacancy_id=vacancy_id, candidate_id=candidate_id
    )


async def get_screening(user: User, application_id: int) -> ScreeningStateResponse:
    """Вопросы отбора и уже сохранённые ответы по отклику.

    Эндпоинта чтения вопросов в разделе 27 нет — он добавлен как минимально
    необходимый источник данных для экрана Screening (раздел 61).
    """
    application = await _own_application(user, application_id)
    questions = await _questions(application.vacancy_id)
    answers = await ScreeningAnswer.filter(application_id=application.id).order_by(
        "question_id"
    )

    return ScreeningStateResponse(
        application_id=application.id,
        vacancy_id=application.vacancy_id,
        status=application.status,
        can_submit=application.status in SCREENING_SOURCE_STATUSES,
        questions=[
            ScreeningQuestionRead(
                id=question.id,
                question=question.question,
                type=question.type,
                required=question.required,
                sort_order=question.sort_order,
                rules=public_rules(question),
            )
            for question in questions
        ],
        answers=[
            ScreeningAnswerRead(
                question_id=answer.question_id, value=stored_value(answer.value)
            )
            for answer in answers
        ],
        suggested_answers=(
            [] if answers else await _suggested_answers(user, application, questions)
        ),
    )


async def _suggested_answers(
    user: User, application: Application, questions: list[ScreeningQuestion]
) -> list[ScreeningAnswerRead]:
    """Функция 26 UX-карты: последний ответ кандидата на текстуально тот же
    вопрос другой вакансии, если он ещё не отвечал на этот отклик.

    Совпадение — по точному тексту вопроса без учёта регистра и краевых
    пробелов: разные вакансии формулируют вопросы независимо, и только
    буквальное совпадение гарантирует, что подсказка отвечает на тот же
    вопрос, а не просто на похожий.
    """
    if not questions:
        return []

    past_answers = (
        await ScreeningAnswer.filter(application__candidate_id=user.user_id)
        .exclude(application_id=application.id)
        .order_by("-created_at")
        .select_related("question")
    )
    latest_by_text: dict[str, ScreeningAnswer] = {}
    for answer in past_answers:
        key = answer.question.question.strip().casefold()
        latest_by_text.setdefault(key, answer)

    suggestions: list[ScreeningAnswerRead] = []
    for question in questions:
        match = latest_by_text.get(question.question.strip().casefold())
        if match is not None:
            suggestions.append(
                ScreeningAnswerRead(
                    question_id=question.id, value=stored_value(match.value)
                )
            )
    return suggestions


async def submit_screening(
    user: User, application_id: int, payload: ScreeningSubmitRequest
) -> ScreeningResultResponse:
    """Проходит первичный отбор: сохраняет ответы и выставляет результат.

    Закрытая вакансия отбор не блокирует: раздел 57 запрещает только новые
    отклики, а отклик здесь уже существует. Оставить кандидата в `screening`
    без выхода было бы хуже — работодатель просто не откроет такой отклик.
    """
    application = await _own_application(user, application_id)
    _ensure_submittable(application)

    questions = await _questions(application.vacancy_id)
    await analytics.log_event(
        "screening_started",
        user_id=user.user_id,
        payload={
            "application_id": application.id,
            "vacancy_id": application.vacancy_id,
            "questions": len(questions),
        },
    )

    checks = check_answers(questions, _submitted_values(payload, questions))

    failed_questions = sorted(check.question_id for check in checks if check.blocks)
    criteria_results = await _evaluate_criteria(user, application.vacancy_id)
    # Двух критериев одного типа контракт не запрещает — тип в ответе один
    failed_criteria = list(
        dict.fromkeys(
            result.type for result in criteria_results if result.blocks_feed
        )
    )
    passed = not failed_questions and not failed_criteria
    new_status = (
        ApplicationStatus.PASSED if passed else ApplicationStatus.HARD_FILTER_FAILED
    )

    await _store_result(
        application,
        checks,
        new_status,
        snapshot=_hard_filter_snapshot(criteria_results, failed_questions),
    )

    event_payload: dict[str, Any] = {
        "application_id": application.id,
        "vacancy_id": application.vacancy_id,
    }
    await analytics.log_event(
        "screening_completed", user_id=user.user_id, payload=event_payload
    )
    await analytics.log_event(
        "hard_filter_passed" if passed else "hard_filter_failed",
        user_id=user.user_id,
        payload=event_payload
        | {
            "failed_criteria": [criterion.value for criterion in failed_criteria],
            "failed_questions": failed_questions,
        },
    )
    logger.info(
        "Первичный отбор завершён: отклик=%s статус=%s",
        application.id,
        new_status.value,
    )

    return ScreeningResultResponse(
        application_id=application.id,
        status=new_status,
        failed_criteria=failed_criteria,
        failed_questions=failed_questions,
    )


async def get_application(
    user: User, application_id: int, background_tasks: BackgroundTasks
) -> CandidateApplicationRead:
    """Статус отклика кандидата — переживает перезагрузку экрана (C06/C07).

    `POST /applications/{id}/screening` отдаёт `failed_criteria` только
    синхронно, в момент прохождения отбора. Здесь тот же результат читается
    заново — из снимка `Application.hard_filter_result`, который отбор уже
    сохраняет (см. `_store_result`).
    """
    application = await _own_application(user, application_id)
    vacancy = await Vacancy.get(id=application.vacancy_id)
    vacancy_read = await vacancies_service.read_vacancy_for_candidate(
        vacancy, background_tasks
    )

    match = await Match.get_or_none(application_id=application.id)
    interview_id: int | None = None
    if match is not None:
        interview = await Interview.get_or_none(match_id=match.id)
        interview_id = interview.id if interview is not None else None

    return CandidateApplicationRead(
        id=application.id,
        vacancy_id=application.vacancy_id,
        status=application.status,
        created_at=application.created_at,
        vacancy=vacancy_read,
        failed_criteria=_failed_criteria_from_snapshot(application.hard_filter_result),
        match_id=match.id if match is not None else None,
        interview_id=interview_id,
    )


async def list_my_applications(user: User) -> CandidateApplicationListResponse:
    """Список откликов кандидата для экрана «Мои отклики» (C12 UX-карты,
    функции 27-28): убрать неизвестность после отклика — видно все статусы
    сразу, отсортированные по последнему изменению.
    """
    applications = (
        await Application.filter(candidate_id=user.user_id)
        .order_by("-updated_at")
        .select_related("vacancy")
    )
    scheduled_ids = [
        application.id
        for application in applications
        if application.status == ApplicationStatus.INTERVIEW_SCHEDULED
    ]
    interview_starts: dict[int, datetime] = {}
    if scheduled_ids:
        interviews = await Interview.filter(
            match__application_id__in=scheduled_ids
        ).select_related("match", "slot")
        interview_starts = {
            interview.match.application_id: interview.slot.starts_at
            for interview in interviews
        }
    return CandidateApplicationListResponse(
        items=[
            CandidateApplicationListItem(
                id=application.id,
                vacancy_id=application.vacancy_id,
                vacancy_title=application.vacancy.title,
                company_name=application.vacancy.company_name,
                image_url=application.vacancy.image_url,
                status=application.status,
                interview_starts_at=interview_starts.get(application.id),
                created_at=application.created_at,
                updated_at=application.updated_at,
            )
            for application in applications
        ]
    )


def _failed_criteria_from_snapshot(
    snapshot: dict[str, Any] | None,
) -> list[CriterionType]:
    """Реконструирует `failed_criteria` из снимка отбора.

    Правило то же, что и при самом отборе (`CriterionResult.blocks_feed`,
    `app.matching.rules`): обязательный критерий, который точно не прошёл.
    `dict.fromkeys` — та же защита от дублей типа, что и в `submit_screening`.
    """
    if not snapshot:
        return []
    return list(
        dict.fromkeys(
            CriterionType(criterion["type"])
            for criterion in snapshot.get("criteria", [])
            if criterion.get("required") and criterion.get("passed") is False
        )
    )


async def _own_application(user: User, application_id: int) -> Application:
    """Отклик текущего кандидата.

    Чужой отклик — `404`, а не `403`: существование чужих откликов наружу
    не раскрывается.
    """
    application = await Application.get_or_none(id=application_id)
    if application is None or application.candidate_id != user.user_id:
        raise NotFoundError("Отклик не найден", code="application_not_found")
    return application


def _ensure_submittable(application: Application) -> None:
    """Защита от повторной обработки: отбор проходится один раз."""
    if application.status not in SCREENING_SOURCE_STATUSES:
        raise ConflictError(
            "Первичный отбор по этому отклику уже пройден",
            code="screening_already_completed",
            details={"status": application.status.value},
        )


async def _questions(vacancy_id: int) -> list[ScreeningQuestion]:
    return await ScreeningQuestion.filter(vacancy_id=vacancy_id).order_by(
        "sort_order", "id"
    )


def _submitted_values(
    payload: ScreeningSubmitRequest, questions: list[ScreeningQuestion]
) -> dict[int, Any]:
    """Сводит ответы запроса к значениям по `question_id`."""
    known = {question.id for question in questions}
    values: dict[int, Any] = {}
    unknown: set[int] = set()
    duplicates: set[int] = set()

    for answer in payload.answers:
        if answer.question_id not in known:
            unknown.add(answer.question_id)
            continue
        if answer.question_id in values:
            duplicates.add(answer.question_id)
            continue
        values[answer.question_id] = answer.value

    if unknown:
        raise ValidationError(
            "Вопрос не относится к этой вакансии",
            code="unknown_question",
            details={"question_ids": sorted(unknown)},
        )
    if duplicates:
        raise ValidationError(
            "Ответ на вопрос передан дважды",
            code="duplicate_answer",
            details={"question_ids": sorted(duplicates)},
        )
    return values


async def _evaluate_criteria(user: User, vacancy_id: int) -> list[CriterionResult]:
    """Проверяет кандидата по критериям вакансии.

    Правила те же, что в ленте: критерий, который проверить нечем (нет данных
    в профиле или неизвестный формат значения), кандидата не отсекает.
    Критерий неизвестного типа не читается по той же причине, что и в ленте:
    проверить его всё равно нечем, а чтение всей вакансии он бы сломал.
    """
    vacancy = await Vacancy.get_or_none(id=vacancy_id)
    if vacancy is None:
        # FK с каскадом: вакансии без отклика не бывает
        raise NotFoundError("Вакансия не найдена", code="vacancy_not_found")

    criteria = await VacancyCriterion.filter(
        vacancy_id=vacancy_id, type__in=list(CriterionType)
    )
    profile = await CandidateProfile.get_or_none(user_id=user.user_id)
    if profile is None:
        logger.info("Первичный отбор без профиля кандидата: проверять нечем")

    return evaluate_vacancy(vacancy, criteria, profile)


def _hard_filter_snapshot(
    criteria_results: list[CriterionResult], failed_questions: list[int]
) -> dict[str, Any]:
    """Снимок обязательных фильтров на момент отбора.

    Он и попадает в карточку работодателя. Пересчитывать результат позже
    нельзя: кандидат может изменить профиль после отбора, и карточка начнёт
    противоречить статусу отклика — отбор пройден, а условия показываются
    проваленными.
    """
    return {
        "criteria": [
            {
                "type": result.type.value,
                "required": result.required,
                "passed": result.passed,
            }
            for result in criteria_results
        ],
        "failed_questions": failed_questions,
    }


async def _store_result(
    application: Application,
    checks: list[AnswerCheck],
    new_status: ApplicationStatus,
    *,
    snapshot: dict[str, Any],
) -> None:
    """Сохраняет ответы и статус одной транзакцией.

    Отклик блокируется, а статус перепроверяется под блокировкой: два
    одновременных запроса не должны пройти отбор дважды и нарушить
    `UNIQUE(application_id, question_id)`.
    """
    async with in_transaction() as connection:
        locked = await (
            Application.filter(id=application.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        _ensure_submittable(locked)

        if checks:
            await ScreeningAnswer.bulk_create(
                [
                    ScreeningAnswer(
                        application_id=locked.id,
                        question_id=check.question_id,
                        # Значение оборачивается в объект: JSONB-скаляр
                        # труднее расширять, а формат ответа ещё может
                        # обрасти полями
                        value={"value": check.value},
                    )
                    for check in checks
                ],
                using_db=connection,
            )

        locked.status = new_status
        locked.hard_filter_result = snapshot
        await locked.save(
            using_db=connection,
            update_fields=["status", "hard_filter_result", "updated_at"],
        )

    application.status = new_status
    application.hard_filter_result = snapshot
