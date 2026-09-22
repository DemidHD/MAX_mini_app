"""Общие фикстуры тестов.

Тесты работают с отдельной базой `<db>_test`: она пересоздаётся перед сессией
и удаляется после, чтобы не трогать данные разработки.

Подключение к БД поднимается тем же lifespan, что и в бою, причём в отдельной
задаче — иначе тесты не заметят, что контекст Tortoise не виден обработчикам
запросов, как это было с голым `Tortoise.init()`.
"""

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import AsyncIterator, Iterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.core.config import settings
from app.core.database import TORTOISE_ORM
from app.main import app, lifespan
from tests.factories import TEST_BOT_TOKEN

_DEV_DSN: str = TORTOISE_ORM["connections"]["default"]
_TEST_DB_NAME = f"{urlparse(_DEV_DSN).path.lstrip('/')}_test"


def _test_dsn() -> str:
    parsed = urlparse(_DEV_DSN)
    return urlunparse(parsed._replace(path=f"/{_TEST_DB_NAME}"))


async def _run_on_dev_database(statement: str) -> None:
    connection = await asyncpg.connect(_DEV_DSN)
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _database(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[None]:
    original_storage_root = settings.storage_root
    settings.storage_root = tmp_path_factory.mktemp("storage")

    # FORCE отцепляет соединения, оставшиеся от прошлого прогона
    await _run_on_dev_database(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
    await _run_on_dev_database(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    TORTOISE_ORM["connections"]["default"] = _test_dsn()

    started = asyncio.Event()
    stop = asyncio.Event()

    async def run_lifespan() -> None:
        async with lifespan(app):
            started.set()
            await stop.wait()

    lifespan_task = asyncio.create_task(run_lifespan())
    started_task = asyncio.create_task(started.wait())
    try:
        done, _ = await asyncio.wait(
            {lifespan_task, started_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if lifespan_task in done:
            # Если lifespan упал до запуска, не зависаем на started.wait().
            started_task.cancel()
            with suppress(asyncio.CancelledError):
                await started_task
            await lifespan_task

        await started_task
        # Миграции в тестах не гоняем: схема строится из тех же моделей
        await Tortoise.generate_schemas()
        yield
    finally:
        stop.set()
        if not lifespan_task.done():
            await lifespan_task
        elif not lifespan_task.cancelled():
            lifespan_task.exception()
        TORTOISE_ORM["connections"]["default"] = _DEV_DSN
        settings.storage_root = original_storage_root
        await _run_on_dev_database(
            f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)'
        )


@pytest.fixture(scope="session", autouse=True)
def _bot_token() -> Iterator[None]:
    """Тесты подписывают initData тестовым токеном, а не боевым."""
    original = settings.max_bot_token
    settings.max_bot_token = TEST_BOT_TOKEN
    yield
    settings.max_bot_token = original


@pytest.fixture
def storage_root(tmp_path: Path) -> Iterator[Path]:
    """Файловое хранилище на время теста — во временном каталоге."""
    original = settings.storage_root
    settings.storage_root = tmp_path
    (tmp_path / "avatars").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    settings.storage_root = original


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
