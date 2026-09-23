"""Проверка `initData` и файлового хранилища по веткам. Разделы 3, 6, 77.

Модульные тесты без базы и HTTP: здесь проверяется то, что решает, пустят ли
чужого внутрь и что случится с файлами при сбое. Сценарные проверки тех же
механизмов — в `test_auth.py` и `test_avatar.py`.
"""

import hmac
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from app.auth.init_data import InitDataError, validate_init_data
from app.core.config import settings
from app.core.errors import ValidationError
from app.core.storage import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    delete_file,
    detect_avatar_mime,
    ensure_avatar_size,
    resolve_stored_file,
    save_avatar,
)
from tests.factories import JPEG_BYTES, PNG_BYTES, TEST_BOT_TOKEN

MAX_AGE = 86400


def _sign(params: dict[str, str], bot_token: str = TEST_BOT_TOKEN) -> str:
    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), sha256).digest()
    return hmac.new(secret_key, launch_params.encode(), sha256).hexdigest()


def _init_data(params: dict[str, str], *, signature: str | None = None) -> str:
    """Собирает initData из произвольных параметров с корректной подписью."""
    encoded = "&".join(
        f"{key}={quote(value, safe='')}" for key, value in params.items()
    )
    return f"{encoded}&hash={signature or _sign(params)}"


def _params(**overrides: Any) -> dict[str, str]:
    moment = datetime.now(timezone.utc)
    params = {
        "auth_date": str(int(moment.timestamp())),
        "user": json.dumps(
            {"id": 100500, "first_name": "Иван"}, ensure_ascii=False, separators=(",", ":")
        ),
    }
    params.update({key: value for key, value in overrides.items() if value is not None})
    for key, value in overrides.items():
        if value is None:
            params.pop(key, None)
    return params


def _validate(init_data: str, *, now: datetime | None = None):
    return validate_init_data(
        init_data, bot_token=TEST_BOT_TOKEN, max_age_seconds=MAX_AGE, now=now
    )


# --- initData: успешный разбор ----------------------------------------------


def test_valid_init_data_is_parsed() -> None:
    result = _validate(_init_data(_params()))

    assert result.user.user_id == 100500
    assert result.user.first_name == "Иван"


def test_optional_user_fields_are_read() -> None:
    user = {
        "id": 100501,
        "first_name": "Иван",
        "last_name": "Петров",
        "username": "ivan",
        "language_code": "ru",
    }
    params = _params(user=json.dumps(user, ensure_ascii=False, separators=(",", ":")))

    result = _validate(_init_data(params))

    assert result.user.last_name == "Петров"
    assert result.user.username == "ivan"
    assert result.user.language_code == "ru"


# --- initData: отказы -------------------------------------------------------


def test_missing_bot_token_is_configuration_error() -> None:
    """Без токена проверку провести нечем — и пропускать никого нельзя."""
    with pytest.raises(InitDataError):
        validate_init_data(
            _init_data(_params()), bot_token="", max_age_seconds=MAX_AGE
        )


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate("")


def test_wrong_signature_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate(_init_data(_params(), signature="0" * 64))


def test_signature_of_other_bot_is_rejected() -> None:
    params = _params()

    with pytest.raises(InitDataError):
        _validate(_init_data(params, signature=_sign(params, "чужой-токен")))


@pytest.mark.parametrize(
    "raw",
    [
        "простотекст",
        "auth_date",
        "&&&",
        "=значение&hash=abc",
    ],
)
def test_malformed_init_data_is_rejected(raw: str) -> None:
    with pytest.raises(InitDataError):
        _validate(raw)


def test_duplicated_hash_is_rejected() -> None:
    """Два `hash` — попытка подобрать тот, который проверит сервер."""
    params = _params()
    correct = _init_data(params)

    with pytest.raises(InitDataError):
        _validate(f"{correct}&hash={'0' * 64}")


def test_init_data_without_hash_is_rejected() -> None:
    params = _params()
    encoded = "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())

    with pytest.raises(InitDataError):
        _validate(encoded)


def test_missing_auth_date_is_rejected() -> None:
    params = {"user": _params()["user"]}

    with pytest.raises(InitDataError):
        _validate(_init_data(params))


@pytest.mark.parametrize("raw", ["вчера", "", "99999999999999999999"])
def test_broken_auth_date_is_rejected(raw: str) -> None:
    with pytest.raises(InitDataError):
        _validate(_init_data(_params(auth_date=raw)))


def test_auth_date_from_future_is_rejected() -> None:
    """Время из будущего — признак подделки, а не часовых поясов."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)

    with pytest.raises(InitDataError):
        _validate(_init_data(_params(auth_date=str(int(future.timestamp())))))


def test_stale_init_data_is_rejected() -> None:
    old = datetime.now(timezone.utc) - timedelta(seconds=MAX_AGE + 60)

    with pytest.raises(InitDataError):
        _validate(_init_data(_params(auth_date=str(int(old.timestamp())))))


@pytest.mark.parametrize(
    "user",
    [
        None,
        "",
        "не json",
        json.dumps(["массив"]),
        json.dumps({"first_name": "Иван"}),
        json.dumps({"id": "100500", "first_name": "Иван"}),
        json.dumps({"id": 100500}),
        json.dumps({"id": 100500, "first_name": "   "}),
    ],
)
def test_broken_user_payload_is_rejected(user: str | None) -> None:
    params = _params()
    if user is None:
        params.pop("user")
    else:
        params["user"] = user

    with pytest.raises(InitDataError):
        _validate(_init_data(params))


# --- Файловое хранилище -----------------------------------------------------


def test_mime_is_detected_by_content() -> None:
    assert detect_avatar_mime(PNG_BYTES) == "image/png"
    assert detect_avatar_mime(JPEG_BYTES) == "image/jpeg"


def test_unknown_content_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        detect_avatar_mime(b"#!/bin/sh\nrm -rf /")


def test_riff_container_without_webp_marker_is_rejected() -> None:
    """RIFF — это не только WebP: без маркера формата файл не принимается."""
    with pytest.raises(UnsupportedFileTypeError):
        detect_avatar_mime(b"RIFF" + b"\x00" * 4 + b"AVI " + b"\x00" * 16)


def test_type_outside_allowed_list_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "avatar_allowed_mime_types", ["image/jpeg"])

    with pytest.raises(UnsupportedFileTypeError):
        detect_avatar_mime(PNG_BYTES)


def test_size_limits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "avatar_max_size_bytes", 100)

    ensure_avatar_size(100)
    with pytest.raises(FileTooLargeError):
        ensure_avatar_size(101)
    with pytest.raises(ValidationError) as empty:
        ensure_avatar_size(0)
    assert empty.value.code == "empty_file"


def test_avatar_is_saved_inside_storage(storage_root: Path) -> None:
    path = save_avatar(100500, PNG_BYTES, "image/png")

    assert path.read_bytes() == PNG_BYTES
    assert path.parent == storage_root / "avatars" / "100500"
    # Имя файла не содержит пользовательских данных
    assert path.name.startswith("avatar-") and path.suffix == ".png"


def test_failed_write_leaves_no_temporary_file(
    storage_root: Path, monkeypatch
) -> None:
    """Сбой записи не должен оставлять мусор в хранилище."""

    def _broken_replace(self, target):  # noqa: ANN001
        raise OSError("диск переполнен")

    monkeypatch.setattr(Path, "replace", _broken_replace)

    with pytest.raises(OSError):
        save_avatar(100501, PNG_BYTES, "image/png")

    directory = storage_root / "avatars" / "100501"
    assert list(directory.iterdir()) == []


def test_delete_file_ignores_paths_outside_storage(
    storage_root: Path, tmp_path: Path
) -> None:
    """Путь за пределами хранилища не удаляется, даже если он существует."""
    outsider = tmp_path.parent / "чужой.txt"
    outsider.write_text("важные данные", encoding="utf-8")

    delete_file(outsider)

    assert outsider.exists()
    outsider.unlink()


def test_delete_file_accepts_missing_and_empty_paths(storage_root: Path) -> None:
    delete_file(None)
    delete_file("")
    delete_file(storage_root / "avatars" / "нет-такого.png")


def test_delete_file_survives_filesystem_error(
    storage_root: Path, monkeypatch
) -> None:
    """Ошибка удаления не должна ломать уже зафиксированную операцию БД."""
    path = save_avatar(100502, PNG_BYTES, "image/png")

    def _broken_unlink(self, missing_ok=False):  # noqa: ANN001, FBT002
        raise OSError("файл занят")

    monkeypatch.setattr(Path, "unlink", _broken_unlink)

    delete_file(path)


def test_resolve_stored_file_checks_location_and_existence(
    storage_root: Path, tmp_path: Path
) -> None:
    saved = save_avatar(100503, PNG_BYTES, "image/png")
    outsider = tmp_path.parent / "чужой.png"
    outsider.write_bytes(PNG_BYTES)

    assert resolve_stored_file(saved) == saved.resolve()
    assert resolve_stored_file(None) is None
    assert resolve_stored_file(outsider) is None
    assert resolve_stored_file(storage_root / "avatars" / "нет.png") is None

    outsider.unlink()


def test_traversal_path_is_not_resolved(storage_root: Path) -> None:
    """`..` в пути не должен выводить за пределы хранилища."""
    escaping = storage_root / "avatars" / ".." / ".." / ".." / "etc" / "passwd"

    assert resolve_stored_file(escaping) is None
