"""Бизнес-логика пользователя: профиль, роль, аватарка. Разделы 8, 9, 27."""

import logging
from pathlib import Path

from tortoise.transactions import in_transaction

from app.analytics import service as analytics
from app.core.database import utcnow
from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.core.storage import (
    delete_file,
    detect_avatar_mime,
    ensure_avatar_size,
    resolve_stored_file,
    save_avatar,
)
from app.users.models import User
from app.users.schemas import ProfileUpdateRequest

logger = logging.getLogger("app.users")


async def update_profile(user: User, payload: ProfileUpdateRequest) -> User:
    """Меняет имя и фамилию только текущего пользователя."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return user

    for field, value in changes.items():
        setattr(user, field, value)
    await user.save(update_fields=[*changes.keys(), "updated_at"])
    return user


async def select_role(user: User, role: UserRole) -> User:
    """Назначает роль текущему пользователю (раздел 9).

    Тех-дока не запрещает сменить уже выбранную роль, поэтому смена
    разрешена; повторная установка той же роли ничего не меняет.
    """
    if user.role == role:
        return user

    previous_role = user.role
    user.role = role
    await user.save(update_fields=["role", "updated_at"])
    await analytics.log_event(
        "role_selected",
        user_id=user.user_id,
        payload={
            "role": role.value,
            "previous_role": previous_role.value if previous_role else None,
        },
    )
    return user


async def set_avatar(user: User, content: bytes) -> User:
    """Устанавливает или заменяет аватарку.

    Старый файл удаляется только после успешной записи нового (раздел 27).
    """
    ensure_avatar_size(len(content))
    mime = detect_avatar_mime(content)

    new_path = save_avatar(user.user_id, content, mime)
    previous_path: str | None = None
    updated_at = utcnow()
    try:
        async with in_transaction() as connection:
            locked_user = await (
                User.filter(user_id=user.user_id)
                .using_db(connection)
                .select_for_update()
                .get()
            )
            previous_path = locked_user.avatar_path
            locked_user.avatar_path = str(new_path)
            locked_user.avatar_updated_at = updated_at
            await locked_user.save(
                using_db=connection,
                update_fields=["avatar_path", "avatar_updated_at", "updated_at"],
            )
    except Exception:
        delete_file(new_path)
        raise

    user.avatar_path = str(new_path)
    user.avatar_updated_at = updated_at
    if previous_path:
        delete_file(previous_path)
    return user


async def delete_avatar(user: User) -> None:
    """Удаляет файл и очищает поля. Отсутствие аватарки — не ошибка сценария."""
    async with in_transaction() as connection:
        locked_user = await (
            User.filter(user_id=user.user_id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        previous_path = locked_user.avatar_path
        if not previous_path:
            raise NotFoundError("Аватарка не установлена", code="avatar_not_found")

        locked_user.avatar_path = None
        locked_user.avatar_updated_at = None
        await locked_user.save(
            using_db=connection,
            update_fields=["avatar_path", "avatar_updated_at", "updated_at"],
        )

    user.avatar_path = None
    user.avatar_updated_at = None
    delete_file(previous_path)


def get_avatar_file(user: User) -> Path:
    """Путь к аватарке текущего пользователя.

    Путь берётся из записи пользователя сессии, поэтому чужой файл получить
    нельзя; дополнительно проверяется, что он лежит внутри хранилища.
    """
    path = resolve_stored_file(user.avatar_path)
    if path is None:
        raise NotFoundError("Аватарка не установлена", code="avatar_not_found")
    return path
