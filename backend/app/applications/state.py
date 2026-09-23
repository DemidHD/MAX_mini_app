"""State machine отклика. Раздел 26 тех-доки.

Один источник правды по допустимым переходам: раздел 26 рисует сценарий
целиком, а реализуется он по этапам, поэтому карта заведена сразу полностью
и помечена, кто каким переходом пользуется.

Статусы меняет только backend — frontend их не выставляет.

Про `under_review`: тех-дока нигде не называет действие, которое его
выставляет, а единственный экран, где он различим, — доска статусов
(раздел 62), и она относится к P1 (раздел 2). Поэтому в P0 отклик идёт из
`passed` сразу в решение работодателя, а `under_review` остаётся заведённым,
но незанятым. Когда в P1 появится триггер, решение должно приниматься и из
`passed`, и из `under_review`: работодатель может нажать «Пригласить» прямо
из списка, не открывая карточку.
"""

from app.core.enums import ApplicationStatus
from app.core.errors import ConflictError

# Откуда можно уйти в первичный отбор (этап 4). Раздел 32 переводит отклик
# в `screening` сразу при создании, но `created` принимается наравне с ним.
SCREENING_SOURCE_STATUSES = (
    ApplicationStatus.CREATED,
    ApplicationStatus.SCREENING,
)

ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    # Этап 4 — первичный отбор
    ApplicationStatus.CREATED: frozenset(
        {
            ApplicationStatus.SCREENING,
            ApplicationStatus.PASSED,
            ApplicationStatus.HARD_FILTER_FAILED,
        }
    ),
    ApplicationStatus.SCREENING: frozenset(
        {ApplicationStatus.PASSED, ApplicationStatus.HARD_FILTER_FAILED}
    ),
    # Этап 5 — решение работодателя. `reserved` — P1 (раздел 20)
    ApplicationStatus.PASSED: frozenset(
        {ApplicationStatus.INVITED, ApplicationStatus.REJECTED}
    ),
    # P1 — заполняется вместе с доской статусов и резервом
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {ApplicationStatus.INVITED, ApplicationStatus.REJECTED}
    ),
    # Этап 6 — взаимный интерес и интервью. Подтверждения от кандидата нет:
    # он уже выразил интерес откликом, последнее слово за работодателем, и
    # match создаётся самим приглашением. Поэтому `invited` — переходное
    # состояние внутри одной операции, а не ожидание действия кандидата.
    ApplicationStatus.INVITED: frozenset({ApplicationStatus.MUTUAL_INTEREST}),
    ApplicationStatus.MUTUAL_INTEREST: frozenset(
        {ApplicationStatus.INTERVIEW_SCHEDULED}
    ),
    ApplicationStatus.INTERVIEW_SCHEDULED: frozenset(
        {ApplicationStatus.INTERVIEW_COMPLETED}
    ),
    # Конечные состояния P0
    ApplicationStatus.HARD_FILTER_FAILED: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.INTERVIEW_COMPLETED: frozenset(),
}


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def ensure_transition(
    current: ApplicationStatus,
    target: ApplicationStatus,
    *,
    code: str = "invalid_state_transition",
    message: str = "Недопустимый переход статуса отклика",
) -> None:
    """Раздел 57: недопустимый переход состояния — `409 Conflict`."""
    if not can_transition(current, target):
        raise ConflictError(
            message,
            code=code,
            details={"status": current.value, "target": target.value},
        )
