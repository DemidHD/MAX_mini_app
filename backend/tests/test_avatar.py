"""Аватарка пользователя. Раздел 27 тех-доки."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.users import service as user_service
from app.users.models import User
from tests.factories import JPEG_BYTES, PNG_BYTES, build_init_data, max_user_payload


async def _login(client: AsyncClient, user_id: int) -> None:
    response = await client.post(
        "/api/auth/max",
        json={"init_data": build_init_data(user=max_user_payload(user_id=user_id))},
    )
    assert response.status_code == 200


def _upload(content: bytes, name: str, mime: str) -> dict:
    return {"file": (name, content, mime)}


async def test_avatar_lifecycle(client: AsyncClient, storage_root: Path) -> None:
    await _login(client, 730001)

    # 1. Загрузка сохраняет файл и отдаёт его обратно
    set_response = await client.patch(
        "/api/users/me/avatar", files=_upload(PNG_BYTES, "avatar.png", "image/png")
    )
    assert set_response.status_code == 200
    body = set_response.json()
    assert body["has_avatar"] is True
    assert body["avatar_updated_at"] is not None
    stored = await User.get(user_id=730001)
    assert Path(stored.avatar_path).is_file()
    assert Path(stored.avatar_path).parent == storage_root / "avatars" / "730001"
    download = await client.get("/api/users/me/avatar")
    assert download.status_code == 200
    assert download.content == PNG_BYTES

    # 2. Замена аватарки удаляет предыдущий файл
    first_path = Path(stored.avatar_path)
    await client.patch(
        "/api/users/me/avatar", files=_upload(JPEG_BYTES, "avatar.jpg", "image/jpeg")
    )
    second_path = Path((await User.get(user_id=730001)).avatar_path)
    assert second_path != first_path
    assert second_path.is_file()
    assert first_path.exists() is False

    # 3. Удаление аватарки убирает файл и ссылку на него
    delete_response = await client.delete("/api/users/me/avatar")
    assert delete_response.status_code == 204
    assert second_path.exists() is False
    final = await User.get(user_id=730001)
    assert final.avatar_path is None
    assert final.avatar_updated_at is None


async def test_avatar_validation_and_access_guards(
    client: AsyncClient, storage_root: Path
) -> None:
    # 1. Без сессии оба эндпоинта недоступны
    for request in (
        client.get("/api/users/me/avatar"),
        client.delete("/api/users/me/avatar"),
    ):
        response = await request
        assert response.status_code == 401

    # 2. У пользователя без аватарки — 404
    await _login(client, 730004)
    missing = await client.get("/api/users/me/avatar")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "avatar_not_found"

    # 3. Файл, замаскированный под картинку, отклоняется по содержимому,
    # а не по расширению или content-type
    disguised = await client.patch(
        "/api/users/me/avatar",
        files=_upload(b"#!/bin/sh\nrm -rf /", "avatar.png", "image/png"),
    )
    assert disguised.status_code == 422
    assert disguised.json()["error"]["code"] == "unsupported_file_type"
    assert (await User.get(user_id=730004)).avatar_path is None

    # 4. Слишком большой файл отклоняется
    oversized = PNG_BYTES + b"\x00" * settings.avatar_max_size_bytes
    too_large = await client.patch(
        "/api/users/me/avatar", files=_upload(oversized, "avatar.png", "image/png")
    )
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "file_too_large"
    assert (await User.get(user_id=730004)).avatar_path is None

    # 5. Чужую аватарку прочитать нельзя, даже зная путь к файлу: путь
    # берётся из записи пользователя сессии, а не из запроса
    await client.patch(
        "/api/users/me/avatar", files=_upload(PNG_BYTES, "avatar.png", "image/png")
    )
    other_path = (await User.get(user_id=730004)).avatar_path

    client.cookies.clear()
    await _login(client, 730008)
    foreign = await client.get("/api/users/me/avatar")
    assert foreign.status_code == 404
    assert Path(other_path).is_file()


async def test_failed_avatar_db_update_removes_new_file(
    client: AsyncClient, storage_root: Path
) -> None:
    await _login(client, 730009)
    user = await User.get(user_id=730009)
    original_save = User.save

    async def fail_avatar_save(instance, *args, **kwargs):
        if "avatar_path" in (kwargs.get("update_fields") or []):
            raise RuntimeError("simulated database failure")
        return await original_save(instance, *args, **kwargs)

    with patch.object(User, "save", new=fail_avatar_save):
        with pytest.raises(RuntimeError, match="simulated database failure"):
            await user_service.set_avatar(user, PNG_BYTES)

    avatar_dir = storage_root / "avatars" / "730009"
    assert list(avatar_dir.glob("avatar-*")) == []
    assert (await User.get(user_id=730009)).avatar_path is None


async def test_failed_avatar_delete_keeps_file_and_database_reference(
    client: AsyncClient, storage_root: Path
) -> None:
    await _login(client, 730010)
    await client.patch(
        "/api/users/me/avatar", files=_upload(PNG_BYTES, "avatar.png", "image/png")
    )
    user = await User.get(user_id=730010)
    stored_path = Path(user.avatar_path)
    original_save = User.save

    async def fail_avatar_save(instance, *args, **kwargs):
        if "avatar_path" in (kwargs.get("update_fields") or []):
            raise RuntimeError("simulated database failure")
        return await original_save(instance, *args, **kwargs)

    with patch.object(User, "save", new=fail_avatar_save):
        with pytest.raises(RuntimeError, match="simulated database failure"):
            await user_service.delete_avatar(user)

    assert stored_path.is_file()
    assert (await User.get(user_id=730010)).avatar_path == str(stored_path)


async def test_concurrent_avatar_updates_leave_only_current_file(
    client: AsyncClient, storage_root: Path
) -> None:
    await _login(client, 730011)
    first_user = await User.get(user_id=730011)
    second_user = await User.get(user_id=730011)

    await asyncio.gather(
        user_service.set_avatar(first_user, PNG_BYTES),
        user_service.set_avatar(second_user, JPEG_BYTES),
    )

    stored = await User.get(user_id=730011)
    avatar_dir = storage_root / "avatars" / "730011"
    files = list(avatar_dir.glob("avatar-*"))
    assert files == [Path(stored.avatar_path)]
    assert list(avatar_dir.glob("*.tmp")) == []
