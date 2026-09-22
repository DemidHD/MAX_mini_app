"""Отклик и всё, что вокруг решения по нему. Разделы 17, 19, 20, 21 тех-доки."""

from tortoise import fields
from tortoise.models import Model

from app.core.enums import ApplicationStatus, DecisionAction, RejectReason


class Application(Model):
    """Отклик кандидата на конкретную вакансию.

    Статус меняет только backend, по state machine из раздела 26.
    """

    id = fields.BigIntField(primary_key=True)
    vacancy = fields.ForeignKeyField(
        "models.Vacancy",
        related_name="applications",
        on_delete=fields.CASCADE,
    )
    candidate = fields.ForeignKeyField(
        "models.User",
        related_name="applications",
        on_delete=fields.CASCADE,
    )
    status = fields.CharEnumField(
        ApplicationStatus,
        max_length=50,
        default=ApplicationStatus.CREATED,
        db_index=True,
    )
    # Снимок обязательных фильтров на момент первичного отбора. Считать его
    # заново по текущему профилю нельзя: кандидат мог изменить профиль после
    # отбора, и карточка начала бы противоречить статусу отклика — человек
    # отбор прошёл, а условия показывались бы проваленными.
    hard_filter_result = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "applications"
        # Повторный отклик на ту же вакансию невозможен (раздел 17)
        unique_together = (("vacancy", "candidate"),)
        indexes = (("vacancy_id",), ("candidate_id",))

    def __str__(self) -> str:
        return f"Application({self.pk})"


class ScreeningAnswer(Model):
    """Ответ кандидата на вопрос первичного отбора в рамках конкретного отклика.

    Исторические ответы не переписываются при изменении профиля кандидата.
    """

    id = fields.BigIntField(primary_key=True)
    application = fields.ForeignKeyField(
        "models.Application",
        related_name="screening_answers",
        on_delete=fields.CASCADE,
    )
    question = fields.ForeignKeyField(
        "models.ScreeningQuestion",
        related_name="answers",
        on_delete=fields.CASCADE,
    )
    value = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "screening_answers"
        unique_together = (("application", "question"),)


class EmployerDecision(Model):
    """История решений работодателя по отклику.

    `reserved` заведён в enum заранее, но до реализации P1 backend его не принимает.
    """

    id = fields.BigIntField(primary_key=True)
    application = fields.ForeignKeyField(
        "models.Application",
        related_name="decisions",
        on_delete=fields.CASCADE,
    )
    action = fields.CharEnumField(DecisionAction, max_length=30)
    reject_reason = fields.CharEnumField(RejectReason, max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "employer_decisions"
        indexes = (("application_id",),)


class Match(Model):
    """Факт взаимного интереса. На один отклик приходится не более одного match."""

    id = fields.BigIntField(primary_key=True)
    application = fields.OneToOneField(
        "models.Application",
        related_name="match",
        on_delete=fields.CASCADE,
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "matches"

    def __str__(self) -> str:
        return f"Match({self.pk})"
