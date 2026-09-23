"""Сервис уведомлений MAX. Разделы 44, 46-50 тех-доки.

Единственное место, которое отправляет сообщения пользователям: бизнес-код
вызывает методы этого сервиса и никогда не работает с ботом напрямую
(раздел 44).

Три правила, которые здесь важнее всего:

- ошибка уведомления не отменяет бизнес-операцию (разделы 47, 57, 83) —
  наружу отсюда не выходит ни одно исключение;
- повторная обработка события не шлёт второе сообщение (раздел 50) — ключ
  `event_type + entity_id + user_id` уникален в `notification_logs`;
- временная ошибка приводит к повтору отправки (раздел 49), но не создаёт
  новых сущностей.

Отправка выполняется в том же запросе, после commit. Очередь и фоновые
повторы (Redis, раздел 72) в P0 не заводятся: нагрузка микробизнеса этого не
требует, а лишняя инфраструктура сделала бы обязательный маршрут зависимым от
внешнего сервиса, что запрещено разделом 83.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from tortoise.exceptions import IntegrityError

from app.analytics import service as analytics
from app.core.config import settings
from app.core.enums import NotificationStatus, NotificationType
from app.notifications import messages
from app.notifications.models import NotificationLog
from app.notifications.transport import (
    NotificationsDisabledError,
    NotificationTransport,
    build_transport,
)

logger = logging.getLogger("app.notifications")


@dataclass(frozen=True)
class SlotRecipient:
    """Кандидат, которому предложено время: кому писать и про какой отклик."""

    user_id: int
    application_id: int


class NotificationService:
    """Отправка уведомлений P0 (раздел 46)."""

    def __init__(self, transport: NotificationTransport | None = None) -> None:
        self._transport = transport

    @property
    def transport(self) -> NotificationTransport:
        if self._transport is None:
            self._transport = build_transport()
        return self._transport

    def set_transport(self, transport: NotificationTransport | None) -> None:
        """Подменяет канал доставки. Нужен тестам и композиции приложения."""
        self._transport = transport

    async def application_created(
        self, *, employer_id: int, application_id: int, vacancy_title: str
    ) -> None:
        """Работодателю: на вакансию поступил новый отклик."""
        await self._deliver(
            NotificationType.APPLICATION_CREATED,
            user_id=employer_id,
            entity_id=application_id,
            text=messages.application_created(vacancy_title=vacancy_title),
        )

    async def candidate_invited(
        self, *, candidate_id: int, application_id: int, vacancy_title: str
    ) -> None:
        """Кандидату: работодатель пригласил его к следующему шагу."""
        await self._deliver(
            NotificationType.CANDIDATE_INVITED,
            user_id=candidate_id,
            entity_id=application_id,
            text=messages.candidate_invited(
                vacancy_title=vacancy_title, application_id=application_id
            ),
        )

    async def mutual_interest(
        self,
        *,
        match_id: int,
        application_id: int,
        candidate_id: int,
        employer_id: int,
        vacancy_title: str,
    ) -> None:
        """Обеим сторонам: возник взаимный интерес.

        Тексты разные: кандидату — выбрать время, работодателю — предложить
        его. Сущность события одна (match), поэтому ключ идемпотентности у
        обоих получателей общий по `entity_id` и разный по `user_id`.
        """
        await self._deliver(
            NotificationType.MUTUAL_INTEREST,
            user_id=candidate_id,
            entity_id=match_id,
            text=messages.mutual_interest_for_candidate(
                vacancy_title=vacancy_title, application_id=application_id
            ),
        )
        await self._deliver(
            NotificationType.MUTUAL_INTEREST,
            user_id=employer_id,
            entity_id=match_id,
            text=messages.mutual_interest_for_employer(vacancy_title=vacancy_title),
        )

    async def interview_slot_available(
        self,
        *,
        vacancy_id: int,
        vacancy_title: str,
        recipients: Sequence[SlotRecipient],
    ) -> None:
        """Кандидатам со взаимным интересом: появилось время для выбора.

        Сущность события — вакансия, а не слот: работодатель заводит слоты
        подряд, и на каждый писать кандидату значит прислать ему пять
        одинаковых сообщений за минуту. Раздел 46 описывает событие как
        «работодатель предоставил доступные слоты», поэтому на вакансию
        приходится одно сообщение, а все свободные времена кандидат видит
        на экране отклика.
        """
        for recipient in recipients:
            await self._deliver(
                NotificationType.INTERVIEW_SLOT_AVAILABLE,
                user_id=recipient.user_id,
                entity_id=vacancy_id,
                text=messages.interview_slot_available(
                    vacancy_title=vacancy_title,
                    application_id=recipient.application_id,
                ),
            )

    async def interview_booked(
        self,
        *,
        interview_id: int,
        application_id: int,
        candidate_id: int,
        employer_id: int,
        vacancy_title: str,
        starts_at: datetime,
    ) -> None:
        """Обеим сторонам: собеседование назначено."""
        await self._deliver(
            NotificationType.INTERVIEW_BOOKED,
            user_id=candidate_id,
            entity_id=interview_id,
            text=messages.interview_booked_for_candidate(
                vacancy_title=vacancy_title,
                starts_at=starts_at,
                application_id=application_id,
            ),
        )
        await self._deliver(
            NotificationType.INTERVIEW_BOOKED,
            user_id=employer_id,
            entity_id=interview_id,
            text=messages.interview_booked_for_employer(
                vacancy_title=vacancy_title, starts_at=starts_at
            ),
        )

    async def _deliver(
        self,
        event_type: NotificationType,
        *,
        user_id: int,
        entity_id: int,
        text: str,
    ) -> None:
        """Доставляет одно уведомление одному получателю.

        Исключений не выпускает: раздел 47 запрещает откатывать бизнес-операцию
        из-за уведомления, а вызывающий код к этому моменту уже сделал commit.
        """
        try:
            log = await self._claim(event_type, user_id=user_id, entity_id=entity_id)
            if log is None:
                return
            await self._send_with_retry(log, user_id=user_id, text=text)
        except Exception:  # noqa: BLE001 — уведомление не ломает сценарий
            logger.exception(
                "Не удалось обработать уведомление %s для пользователя %s",
                event_type.value,
                user_id,
            )

    async def _claim(
        self, event_type: NotificationType, *, user_id: int, entity_id: int
    ) -> NotificationLog | None:
        """Заводит запись журнала или возвращает существующую.

        `None` означает «отправлять не нужно»: уведомление уже доставлено
        (раздел 50).
        """
        try:
            log, _ = await NotificationLog.get_or_create(
                event_type=event_type,
                entity_id=entity_id,
                user_id=user_id,
                defaults={"status": NotificationStatus.PENDING},
            )
        except IntegrityError:
            # Параллельный запрос успел завести запись: работаем с ней
            logger.info("Журнал уведомления уже создан параллельным запросом")
            log = await NotificationLog.get(
                event_type=event_type, entity_id=entity_id, user_id=user_id
            )

        if log.status is NotificationStatus.SENT:
            logger.info(
                "Уведомление %s по сущности %s уже доставлено",
                event_type.value,
                entity_id,
            )
            return None
        return log

    async def _send_with_retry(
        self, log: NotificationLog, *, user_id: int, text: str
    ) -> None:
        """Отправляет сообщение, повторяя попытку при временной ошибке."""
        attempts = max(1, settings.notification_max_attempts)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                await self.transport.send(user_id, text)
            except NotificationsDisabledError as error:
                # Канал выключен: повторять нечего, но и отказом это не
                # считается — уведомление останется ожидающим отправки
                await self._finish(
                    log,
                    status=NotificationStatus.PENDING,
                    attempts=log.attempts + attempt,
                    error=str(error),
                )
                return
            except Exception as error:  # noqa: BLE001 — причину знает транспорт
                last_error = error
                logger.warning(
                    "Попытка %s из %s отправить уведомление %s не удалась",
                    attempt,
                    attempts,
                    log.event_type.value,
                )
                if attempt < attempts:
                    await asyncio.sleep(
                        settings.notification_retry_delay_seconds * attempt
                    )
                continue

            await self._finish(
                log,
                status=NotificationStatus.SENT,
                attempts=log.attempts + attempt,
                error=None,
            )
            await analytics.log_event(
                "notification_sent",
                user_id=user_id,
                payload={
                    "event_type": log.event_type.value,
                    "entity_id": log.entity_id,
                    "attempts": log.attempts,
                },
            )
            logger.info(
                "Уведомление %s доставлено пользователю %s",
                log.event_type.value,
                user_id,
            )
            return

        await self._finish(
            log,
            status=NotificationStatus.FAILED,
            attempts=log.attempts + attempts,
            error=_error_text(last_error),
        )
        logger.error(
            "Уведомление %s пользователю %s не доставлено",
            log.event_type.value,
            user_id,
        )

    async def _finish(
        self,
        log: NotificationLog,
        *,
        status: NotificationStatus,
        attempts: int,
        error: str | None,
    ) -> None:
        log.status = status
        log.attempts = attempts
        log.error = error
        await log.save(update_fields=["status", "attempts", "error", "updated_at"])


def _error_text(error: Exception | None) -> str | None:
    """Короткое описание ошибки для журнала.

    Раздел 77: в логи не должны попадать лишние данные, поэтому хранится тип
    и текст исключения, а не тело запроса.
    """
    if error is None:
        return None
    return f"{type(error).__name__}: {error}"[:500]


# Единый экземпляр: бизнес-код обращается к нему, тесты подменяют транспорт
notification_service = NotificationService()
