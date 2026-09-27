"""Загрузка справочника навыков «MAX Найм | Справочник навыков v1.0».

Данные лежат в `app/skills/data/skills.json` и `aliases.json` — не в коде:
это внешний продуктовый артефакт (2166 канонических навыков, 37 категорий,
66 примеров алиасов), а не то, что меняется вместе с кодом. При обновлении
справочника нужно заменить эти два файла и прогнать `scripts/seed_skills.py`
ещё раз — загрузка идемпотентна (по `code` и по `alias`), уже существующие
строки не дублируются.

16 навыков исходного справочника имели одинаковое название в двух разных
категориях (например «Работа с CRM» — и в «Продажи», и в «Цифровые навыки»).
Раздел 4 самого справочника требует «один смысл — один канонический навык»,
поэтому такие позиции схлопнуты в одну запись ещё на этапе подготовки
`skills.json` (оставлена первая по порядку категория, вторая отброшена) —
это уже сделано, здесь только загрузка.
"""

import json
import logging
from pathlib import Path
from typing import Any

from app.skills.models import Skill, SkillAlias

logger = logging.getLogger("app.skills")

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_json(name: str) -> list[dict[str, Any]]:
    with (DATA_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


async def seed_skills_dictionary() -> tuple[int, int]:
    """Создаёт навыки и алиасы справочника, если их ещё нет.

    Возвращает (сколько навыков создано, сколько алиасов создано).
    """
    skills_data = _load_json("skills.json")
    aliases_data = _load_json("aliases.json")

    existing_codes = set(
        await Skill.filter(code__in=[s["code"] for s in skills_data]).values_list(
            "code", flat=True
        )
    )
    to_create = [s for s in skills_data if s["code"] not in existing_codes]
    if to_create:
        await Skill.bulk_create(
            [
                Skill(code=s["code"], name=s["name"], category=s["category"])
                for s in to_create
            ]
        )
    logger.info(
        "Справочник навыков: создано %s из %s", len(to_create), len(skills_data)
    )

    code_to_id = {
        skill.code: skill.id
        for skill in await Skill.filter(
            code__in=[s["code"] for s in skills_data]
        ).only("id", "code")
    }

    existing_aliases = set(
        await SkillAlias.filter(
            alias__in=[a["alias"] for a in aliases_data]
        ).values_list("alias", flat=True)
    )
    aliases_to_create = [
        SkillAlias(alias=a["alias"], skill_id=code_to_id[a["skill_code"]])
        for a in aliases_data
        if a["alias"] not in existing_aliases and a["skill_code"] in code_to_id
    ]
    if aliases_to_create:
        await SkillAlias.bulk_create(aliases_to_create)
    logger.info(
        "Алиасы навыков: создано %s из %s", len(aliases_to_create), len(aliases_data)
    )

    return len(to_create), len(aliases_to_create)
