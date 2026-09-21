"""Pydantic-схемы пользователя. ORM-модели и API-схемы не смешиваются (раздел 52)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import UserRole
from app.users.models import User


class UserRead(BaseModel):
    """Профиль текущего пользователя."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    role: UserRole | None
    has_avatar: bool
    avatar_updated_at: datetime | None

    @classmethod
    def from_user(cls, user: User) -> "UserRead":
        return cls(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=user.language_code,
            role=user.role,
            has_avatar=bool(user.avatar_path),
            avatar_updated_at=user.avatar_updated_at,
        )


class ProfileUpdateRequest(BaseModel):
    """Изменение имени и фамилии.

    Значения, полученные от MAX при первой авторизации, не считаются
    неизменяемыми (раздел 27). `user_id` в теле запроса не принимается.
    """

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @field_validator("first_name")
    @classmethod
    def _require_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Имя не может быть пустым")
        return cleaned

    @field_validator("last_name")
    @classmethod
    def _strip_or_clear(cls, value: str | None) -> str | None:
        """Пустая строка — осознанное удаление фамилии, колонка это допускает."""
        if value is None:
            return None
        return value.strip() or None


class RoleUpdateRequest(BaseModel):
    """Выбор роли. Допустимы только `candidate` и `employer`."""

    role: UserRole
