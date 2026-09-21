"""Общие фикстуры тестов.

Тесты работают с отдельной базой `<db>_test`: она пересоздаётся перед сессией
и удаляется после, чтобы не трогать данные разработки.
"""

from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest_asyncio
from tortoise import Tortoise

from app.core.database import MODELS_MODULES, TORTOISE_ORM

_DEV_DSN: str = TORTOISE_ORM["connections"]["default"]
_TEST_DB_NAME = f"{urlparse(_DEV_DSN).path.lstrip('/')}_test"


def _test_dsn() -> str:
    parsed = urlparse(_DEV_DSN)
    return urlunparse(parsed._replace(path=f"/{_TEST_DB_NAME}"))


async def _recreate_test_database() -> None:
    """FORCE отцепляет зависшие соединения от прошлого прогона."""
    connection = await asyncpg.connect(_DEV_DSN)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    finally:
        await connection.close()


async def _drop_test_database() -> None:
    connection = await asyncpg.connect(_DEV_DSN)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
    finally:
        await connection.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    await _recreate_test_database()
    await Tortoise.init(
        config={
            "connections": {"default": _test_dsn()},
            "apps": {
                "models": {"models": MODELS_MODULES, "default_connection": "default"}
            },
            "use_tz": True,
            "timezone": "UTC",
        }
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()
        await _drop_test_database()
