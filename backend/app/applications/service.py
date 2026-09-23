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
from typing import Any

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.applications.models import Application, ScreeningAnswer
from app.applications.schemas import (
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
from app.matching.rules import CriterionResult, evaluate_vacancy
from app.notifications.service import notification_service
from app.users.models import User
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion

logger = logging.getLogger("app.applications")



async def apply(user: User, vacancy_id: int) -> tuple[Application, bool]:
    """Отклик кандидата на вакансию (раздел 32).

    Проверки в порядке раздела 32: вакансия существует, вакансия
    опубликована, отклик ещё не создан. Роль и личность кандидата уже
    проверены зависимостью — идентификаторы из тела запроса не принимаются.

    Повторный отклик возвращает существующий, а не ошибку (раздел 57), и
    ничего не создаёт (раздел 79). Отдельная транзакция не нужна:
    единственность обеспечивает `UNIQUE(vacancy_id, candidate_id)`, и
    параллельный запрос ловится через `IntegrityError`.

    Уведомление `application_created` работодателю (раздел 46) отправляется
    после создания: ошибка отправки отклик не отменяет (раздел 47).

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

    try:
        application = await Application.create(
            vacancy_id=vacancy.id,
            candidate_id=user.user_id,
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
    await notification_service.application_created(
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
    )


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
