"""Загружает справочник навыков «MAX Найм | Справочник навыков v1.0» из
`app/skills/data/skills.json` и `aliases.json`. Идемпотентно — повторный
запуск после обновления этих файлов добавит только новые записи.

Запуск:
    docker compose exec backend python scripts/seed_skills.py
"""

import asyncio
import sys
from pathlib import Path

from tortoise import Tortoise

# Скрипт запускается как файл, поэтому корень проекта нужно добавить руками
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import TORTOISE_ORM  # noqa: E402
from app.skills.seed import seed_skills_dictionary  # noqa: E402


async def main() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        skills_created, aliases_created = await seed_skills_dictionary()
        print(f"Добавлено новых навыков: {skills_created}")
        print(f"Добавлено новых алиасов: {aliases_created}")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
