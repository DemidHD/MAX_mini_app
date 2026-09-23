"""Проверки готовности P0. Разделы 55, 71, 76, 77 тех-доки.

Эти тесты не про сценарий, а про то, что легко разъезжается при развитии:
ограничения и индексы БД, состав `.env.example`, миграции и то, что в логи
не попадают секреты.
"""

import logging
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from tortoise import Tortoise

from app.core.config import Settings, settings
from app.core.database import MODELS_MODULES
from tests.factories import build_init_data, max_user_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Раздел 55: обязательные уникальные ограничения
REQUIRED_UNIQUE = (
    ("candidate_profiles", ("user_id",)),
    ("applications", ("vacancy_id", "candidate_id")),
    ("screening_answers", ("application_id", "question_id")),
    ("matches", ("application_id",)),
    ("vacancies", ("public_token",)),
    ("referral_links", ("code",)),
    # Ключ идемпотентности уведомлений (раздел 50)
    ("notification_logs", ("event_type", "entity_id", "user_id")),
)

# Раздел 55: обязательные индексы
REQUIRED_INDEXES = (
    ("vacancies", "status"),
    ("vacancies", "employer_id"),
    ("applications", "vacancy_id"),
    ("applications", "candidate_id"),
    ("applications", "status"),
    ("interview_slots", "vacancy_id"),
    ("interview_slots", "starts_at"),
    ("analytics_events", "event_name"),
    ("analytics_events", "timestamp"),
)


async def _indexes() -> list[tuple[str, bool, tuple[str, ...]]]:
    """Индексы тестовой схемы: (таблица, уникальный, колонки)."""
    connection = Tortoise.get_connection("default")
    rows = await connection.execute_query_dict(
        "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'public'"
    )

    parsed: list[tuple[str, bool, tuple[str, ...]]] = []
    for row in rows:
        definition = row["indexdef"]
        columns = re.search(r"\(([^)]*)\)$", definition)
        if columns is None:
            continue
        parsed.append(
            (
                row["tablename"],
                "UNIQUE INDEX" in definition,
                tuple(
                    column.strip().strip('"')
                    for column in columns.group(1).split(",")
                ),
            )
        )
    return parsed


# --- Схема БД ---------------------------------------------------------------


async def test_required_unique_constraints_exist() -> None:
    """Раздел 55: без этих ограничений дубликаты ловятся только кодом."""
    indexes = await _indexes()

    for table, columns in REQUIRED_UNIQUE:
        assert any(
            index_table == table and unique and set(index_columns) == set(columns)
            for index_table, unique, index_columns in indexes
        ), f"нет уникального ограничения {table}{columns}"


async def test_required_indexes_exist() -> None:
    indexes = await _indexes()

    for table, column in REQUIRED_INDEXES:
        assert any(
            index_table == table and column in index_columns
            for index_table, _, index_columns in indexes
        ), f"нет индекса {table}.{column}"


async def test_users_primary_key_is_max_user_id() -> None:
    """Инвариант проекта: отдельного внутреннего идентификатора нет."""
    connection = Tortoise.get_connection("default")
    rows = await connection.execute_query_dict(
        """
        SELECT column_name
        FROM information_schema.key_column_usage AS k
        JOIN information_schema.table_constraints AS c
          ON c.constraint_name = k.constraint_name
        WHERE c.table_name = 'users' AND c.constraint_type = 'PRIMARY KEY'
        """
    )

    assert [row["column_name"] for row in rows] == ["user_id"]


async def test_every_model_module_has_migration() -> None:
    """Таблица, которой нет в миграциях, не появится в боевой БД."""
    migrations = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BACKEND_ROOT / "migrations" / "models").glob("*.py")
    )

    tables = {
        model._meta.db_table
        for app_models in Tortoise.apps.values()
        for model in app_models.values()
        if model._meta.db_table != "aerich"
    }
    assert tables, "модели не загружены"

    missing = sorted(table for table in tables if f'"{table}"' not in migrations)
    assert not missing, f"нет миграции для таблиц: {missing}"


def test_all_model_modules_are_registered() -> None:
    """Модуль моделей, не попавший в конфигурацию, не создаст таблиц."""
    packages = {
        path.parent.name
        for path in (BACKEND_ROOT / "app").glob("*/models.py")
    }
    registered = {module.split(".")[1] for module in MODELS_MODULES if "." in module}

    assert packages <= registered, f"не зарегистрированы: {sorted(packages - registered)}"


# --- Конфигурация -----------------------------------------------------------


def test_env_example_lists_every_setting() -> None:
    """Раздел 71: `.env.example` должен описывать все переменные окружения."""
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented = {
        line.split("=", 1)[0].strip()
        for line in example.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }

    missing = sorted(
        name.upper() for name in Settings.model_fields if name.upper() not in documented
    )
    assert not missing, f"не описаны в .env.example: {missing}"


def test_env_example_has_no_real_secrets() -> None:
    """Секреты в Git не хранятся (раздел 71)."""
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for name in ("MAX_BOT_TOKEN", "MAX_WEBHOOK_SECRET", "SESSION_SECRET", "AI_API_KEY"):
        assert f"{name}=\n" in example or example.rstrip().endswith(f"{name}="), (
            f"{name} в .env.example должен быть пустым"
        )


# --- Логирование ------------------------------------------------------------


async def test_logs_do_not_contain_init_data_or_cookies(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Раздел 77: ни initData, ни cookie, ни токен в логи не пишутся."""
    init_data = build_init_data(user=max_user_payload(user_id=830001))

    with caplog.at_level(logging.DEBUG):
        response = await client.post("/api/auth/max", json={"init_data": init_data})
    assert response.status_code == 200, response.text

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert init_data not in logged
    assert "hash=" not in logged
    assert settings.session_cookie_name not in logged
    assert settings.max_bot_token not in logged


async def test_access_log_records_method_path_and_status(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Раздел 77: строка доступа содержит эндпоинт и код ответа."""
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/health")

    access = [record for record in caplog.records if record.name == "app.access"]
    assert access, "нет строки доступа"
    assert "GET /health -> 200" in access[-1].getMessage()
