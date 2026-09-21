"""Модель пользователя. Раздел 8 тех-доки."""

from tortoise import fields
from tortoise.models import Model

from app.core.database import utcnow
from app.core.enums import UserRole


class User(Model):
    """Пользователь MAX Найм.

    `user_id` из MAX одновременно является первичным ключом в БД.
    Отдельный внутренний идентификатор не создаётся (раздел 8).
    """

    user_id = fields.BigIntField(primary_key=True, generated=False)
    first_name = fields.CharField(max_length=100)
    last_name = fields.CharField(max_length=100, null=True)
    username = fields.CharField(max_length=100, null=True)
    language_code = fields.CharField(max_length=10, null=True)
    # NULL — нормальное состояние нового пользователя: роль выбирается отдельно.
    role = fields.CharEnumField(UserRole, max_length=20, null=True)
    avatar_path = fields.CharField(max_length=500, null=True)
    avatar_updated_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_auth_at = fields.DatetimeField(default=utcnow)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return f"User({self.user_id})"
