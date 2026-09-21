"""Слоты и собеседования. Разделы 22, 23 тех-доки."""

from tortoise import fields
from tortoise.models import Model

from app.core.enums import InterviewSlotStatus, InterviewStatus


class InterviewSlot(Model):
    """Доступный временной интервал работодателя для собеседования."""

    id = fields.BigIntField(primary_key=True)
    employer = fields.ForeignKeyField(
        "models.User",
        related_name="interview_slots",
        on_delete=fields.CASCADE,
    )
    vacancy = fields.ForeignKeyField(
        "models.Vacancy",
        related_name="interview_slots",
        on_delete=fields.CASCADE,
    )
    starts_at = fields.DatetimeField(db_index=True)
    ends_at = fields.DatetimeField()
    status = fields.CharEnumField(
        InterviewSlotStatus,
        max_length=20,
        default=InterviewSlotStatus.AVAILABLE,
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "interview_slots"
        indexes = (("vacancy_id",),)

    def __str__(self) -> str:
        return f"InterviewSlot({self.pk})"


class Interview(Model):
    """Назначенное или проведённое собеседование.

    Слот и match уникальны: два собеседования на один слот создать нельзя.
    """

    id = fields.BigIntField(primary_key=True)
    match = fields.OneToOneField(
        "models.Match",
        related_name="interview",
        on_delete=fields.CASCADE,
    )
    slot = fields.OneToOneField(
        "models.InterviewSlot",
        related_name="interview",
        on_delete=fields.RESTRICT,
    )
    status = fields.CharEnumField(
        InterviewStatus,
        max_length=30,
        default=InterviewStatus.SCHEDULED,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "interviews"

    def __str__(self) -> str:
        return f"Interview({self.pk})"
