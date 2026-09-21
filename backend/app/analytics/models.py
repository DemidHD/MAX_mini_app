"""Журнал аналитических событий. Раздел 25 тех-доки."""

from tortoise import fields
from tortoise.models import Model

from app.core.database import utcnow


class AnalyticsEvent(Model):
    """Событие пользовательского пути.

    Ошибки записи аналитики не должны ломать основной сценарий (раздел 25),
    поэтому сервис аналитики перехватывает их у себя.
    """

    id = fields.BigIntField(primary_key=True)
    # NULL допустим для технических событий без пользователя
    user = fields.ForeignKeyField(
        "models.User",
        related_name="analytics_events",
        null=True,
        on_delete=fields.SET_NULL,
    )
    event_name = fields.CharField(max_length=100, db_index=True)
    payload = fields.JSONField(null=True)
    timestamp = fields.DatetimeField(default=utcnow, db_index=True)

    class Meta:
        table = "analytics_events"

    def __str__(self) -> str:
        return f"AnalyticsEvent({self.event_name})"
