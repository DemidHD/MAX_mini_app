"""Журнал уведомлений. Раздел 48 тех-доки.

Раздел 48 разрешает для P0 обойтись `analytics_events`, но рекомендует
отдельную таблицу, и она здесь нужна по существу: идемпотентность (раздел 50)
и повторная отправка (раздел 49) требуют уникального ключа события, состояния
доставки и числа попыток. В `analytics_events` нет ни уникальности, ни
статуса, а сервис аналитики по разделу 25 намеренно глотает свои ошибки —
источником истины о доставке он быть не может.
"""

from tortoise import fields
from tortoise.models import Model

from app.core.enums import NotificationStatus, NotificationType


class NotificationLog(Model):
    """Одно уведомление одного типа по одной сущности одному получателю.

    Ключ идемпотентности из раздела 50 — `event_type + entity_id + user_id`,
    он же UNIQUE: повторная обработка события не приводит ко второму
    сообщению.
    """

    id = fields.BigIntField(primary_key=True)
    event_type = fields.CharEnumField(NotificationType, max_length=50, db_index=True)
    # Идентификатор сущности события: отклика, match, слота или собеседования.
    # Ссылкой не делается: тип сущности зависит от события.
    entity_id = fields.BigIntField()
    user = fields.ForeignKeyField(
        "models.User",
        related_name="notifications",
        on_delete=fields.CASCADE,
    )
    status = fields.CharEnumField(
        NotificationStatus, max_length=20, default=NotificationStatus.PENDING
    )
    attempts = fields.IntField(default=0)
    # Текст последней ошибки отправки; персональные данные сюда не пишутся
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notification_logs"
        unique_together = (("event_type", "entity_id", "user"),)
        indexes = (("user_id",),)

    def __str__(self) -> str:
        return f"NotificationLog({self.pk})"
