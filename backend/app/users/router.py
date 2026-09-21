"""Эндпоинты пользователя. Раздел 27 тех-доки."""

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from app.auth.dependencies import CurrentUser
from app.core.config import settings
from app.core.storage import ensure_avatar_size
from app.users import service
from app.users.schemas import ProfileUpdateRequest, RoleUpdateRequest, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> UserRead:
    return UserRead.from_user(user)


@router.patch("/me/profile", response_model=UserRead)
async def update_profile(payload: ProfileUpdateRequest, user: CurrentUser) -> UserRead:
    updated = await service.update_profile(user, payload)
    return UserRead.from_user(updated)


@router.patch("/me/role", response_model=UserRead)
async def update_role(payload: RoleUpdateRequest, user: CurrentUser) -> UserRead:
    updated = await service.select_role(user, payload.role)
    return UserRead.from_user(updated)


@router.get("/me/avatar", response_class=FileResponse)
async def get_avatar(user: CurrentUser) -> FileResponse:
    """Отдаёт аватарку текущего пользователя. Чужой файл получить нельзя."""
    path = service.get_avatar_file(user)
    return FileResponse(path)


@router.patch("/me/avatar", response_model=UserRead)
async def set_avatar(
    user: CurrentUser, file: UploadFile = File(...)
) -> UserRead:
    """Устанавливает аватарку, а если она уже есть — заменяет её."""
    # Размер проверяется до чтения тела в память, чтобы не тащить в неё
    # файл произвольного объёма
    if file.size is not None:
        ensure_avatar_size(file.size)
    content = await file.read(settings.avatar_max_size_bytes + 1)
    updated = await service.set_avatar(user, content)
    return UserRead.from_user(updated)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(user: CurrentUser) -> None:
    await service.delete_avatar(user)
