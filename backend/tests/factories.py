"""Вспомогательные генераторы для тестов."""

import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import quote

TEST_BOT_TOKEN = "test-bot-token-0123456789"


def max_user_payload(
    user_id: int = 100500,
    first_name: str = "Иван",
    last_name: str | None = "Петров",
    username: str | None = "ivan_petrov",
    language_code: str | None = "ru",
) -> dict[str, Any]:
    """Пользователь в том виде, в каком его присылает MAX: идентификатор в `id`."""
    return {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "language_code": language_code,
        "photo_url": None,
    }


def build_init_data(
    *,
    user: dict[str, Any] | None = None,
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: datetime | None = None,
    corrupt_hash: bool = False,
) -> str:
    """Собирает initData тем же алгоритмом, что и клиент MAX."""
    moment = auth_date or datetime.now(timezone.utc)
    params = {
        "auth_date": str(int(moment.timestamp())),
        "chat": json.dumps({"id": 12345, "type": "DIALOG"}, separators=(",", ":")),
        "ip": "192.168.0.1",
        "query_id": "4c0ab423-342b-4e45-aea4-2747dbc500cd",
        "user": json.dumps(
            user or max_user_payload(), ensure_ascii=False, separators=(",", ":")
        ),
    }

    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), sha256).digest()
    signature = hmac.new(secret_key, launch_params.encode("utf-8"), sha256).hexdigest()
    if corrupt_hash:
        signature = "0" * 64

    encoded = "&".join(
        f"{key}={quote(value, safe='')}" for key, value in params.items()
    )
    return f"{encoded}&hash={signature}"


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64 + b"\xff\xd9"
