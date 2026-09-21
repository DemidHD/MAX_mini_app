"""Серверные сессии Mini App. Раздел 10 тех-доки."""

import uuid

from tortoise import fields
from tortoise.models import Model

from app.core.database import utcnow


class Session(Model):
    """Связывает cookie браузера с конкретным `users.user_id`.

    Идентификатор сессии не является идентификатором пользователя
    и не передаётся frontend как таковой.
    """

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="sessions",
        on_delete=fields.CASCADE,
    )
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
    last_used_at = fields.DatetimeField(default=utcnow)

    class Meta:
        table = "sessions"
        indexes = (("user_id",),)

    def is_expired(self) -> bool:
        return self.expires_at <= utcnow()
