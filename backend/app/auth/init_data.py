"""Проверка стартовых параметров MAX Mini App.

Алгоритм — раздел 6 тех-доки и документация MAX
(https://dev.max.ru/docs/webapps/validation):

    secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)
    hash       = hex(HMAC_SHA256(key=secret_key, msg=launch_params))

`launch_params` — пары `key=value` с URL-декодированными значениями, без `hash`,
отсортированные по ключу и склеенные через `\n`.

Данные из `initData` считаются доверенными только после успешной проверки подписи.
"""

import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import unquote

from app.core.errors import UnauthorizedError

SECRET_KEY_SALT = b"WebAppData"


@dataclass(frozen=True)
class MaxUser:
    """Пользователь MAX из проверенной `initData`."""

    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None


@dataclass(frozen=True)
class InitData:
    """Результат успешной проверки."""

    user: MaxUser
    auth_date: datetime


class InitDataError(UnauthorizedError):
    """initData не прошла проверку. Наружу отдаётся как 401."""

    code = "invalid_init_data"
    message = "Не удалось проверить данные MAX"


def validate_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> InitData:
    """Проверяет подпись и возраст `initData`, возвращает данные пользователя."""
    if not bot_token:
        # Конфигурационная ошибка: без токена проверку провести нельзя,
        # и молча пропускать пользователя нельзя тем более.
        raise InitDataError("Проверка MAX не настроена")
    if not init_data:
        raise InitDataError("Пустая initData")

    pairs = _parse_pairs(init_data)
    received_hash = _extract_single_hash(pairs)
    launch_params = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs, key=lambda pair: pair[0])
    )

    if not hmac.compare_digest(_sign(launch_params, bot_token), received_hash):
        raise InitDataError("Подпись initData не совпадает")

    auth_date = _parse_auth_date(dict(pairs).get("auth_date"))
    _ensure_fresh(auth_date, max_age_seconds, now or datetime.now(timezone.utc))

    return InitData(user=_parse_user(dict(pairs).get("user")), auth_date=auth_date)


def _parse_pairs(init_data: str) -> list[tuple[str, str]]:
    """Разбирает `key=value&...`, декодируя значения. `hash` пока остаётся в списке."""
    pairs: list[tuple[str, str]] = []
    for chunk in init_data.split("&"):
        if not chunk:
            continue
        key, separator, value = chunk.partition("=")
        if not separator:
            raise InitDataError("Некорректный формат initData")
        pairs.append((key, unquote(value)))
    if not pairs:
        raise InitDataError("Некорректный формат initData")
    return pairs


def _extract_single_hash(pairs: list[tuple[str, str]]) -> str:
    """Вынимает `hash` из списка. Он должен встречаться ровно один раз."""
    hashes = [value for key, value in pairs if key == "hash"]
    if len(hashes) != 1:
        raise InitDataError("Параметр hash должен встречаться ровно один раз")
    pairs[:] = [(key, value) for key, value in pairs if key != "hash"]
    return hashes[0]


def _sign(launch_params: str, bot_token: str) -> str:
    secret_key = hmac.new(
        SECRET_KEY_SALT, bot_token.encode("utf-8"), sha256
    ).digest()
    return hmac.new(secret_key, launch_params.encode("utf-8"), sha256).hexdigest()


def _parse_auth_date(raw: str | None) -> datetime:
    if raw is None:
        raise InitDataError("В initData нет auth_date")
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise InitDataError("Некорректный auth_date") from exc


def _ensure_fresh(auth_date: datetime, max_age_seconds: int, now: datetime) -> None:
    if auth_date > now + timedelta(minutes=5):
        raise InitDataError("auth_date из будущего")
    if now - auth_date > timedelta(seconds=max_age_seconds):
        raise InitDataError("initData устарела")


def _parse_user(raw: str | None) -> MaxUser:
    """Разбирает JSON пользователя. MAX присылает идентификатор в поле `id`."""
    if not raw:
        raise InitDataError("В initData нет пользователя")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("Некорректные данные пользователя") from exc
    if not isinstance(payload, dict):
        raise InitDataError("Некорректные данные пользователя")

    user_id = payload.get("id")
    if not isinstance(user_id, int):
        raise InitDataError("В данных пользователя нет идентификатора")

    first_name = payload.get("first_name")
    if not isinstance(first_name, str) or not first_name.strip():
        raise InitDataError("В данных пользователя нет имени")

    return MaxUser(
        user_id=user_id,
        first_name=first_name.strip()[:100],
        last_name=_optional_str(payload.get("last_name"), 100),
        username=_optional_str(payload.get("username"), 100),
        language_code=_optional_str(payload.get("language_code"), 10),
    )


def _optional_str(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:max_length] or None
