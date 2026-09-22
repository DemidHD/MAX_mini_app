"""Минимальные гарантии отката начальной миграции."""

import importlib.util
from pathlib import Path


async def test_initial_migration_has_safe_downgrade() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "models"
        / "0_20260921155744_init.py"
    )
    spec = importlib.util.spec_from_file_location("initial_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sql = await module.downgrade(None)

    assert 'DROP TABLE IF EXISTS "users"' in sql
    assert 'DROP TABLE IF EXISTS "interviews"' in sql
    # Aerich удаляет запись версии после выполнения SQL, поэтому его служебная
    # таблица должна пережить downgrade.
    assert 'DROP TABLE IF EXISTS "aerich"' not in sql
