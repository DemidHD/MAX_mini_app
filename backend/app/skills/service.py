"""Бизнес-логика справочника навыков. Не из тех-доки — продуктовое решение.

`candidate_profiles.skill_ids` хранит только id из этого справочника —
функции здесь считают из id читаемые названия (для кандидата и работодателя)
и наоборот, проверяют, что присланные id вообще существуют в справочнике.
"""

import re
from typing import Iterable

from app.candidates.models import CandidateProfile
from app.core.errors import ValidationError
from app.skills.models import Skill, SkillAlias
from app.skills.schemas import SkillListResponse, SkillRead

# Не из тех-доки — защита от мусорного запроса, а не продуктовый лимит:
# справочник на масштабе микробизнеса заведомо укладывается в одну страницу.
SKILLS_LIST_LIMIT = 100


async def list_skills(query: str | None) -> SkillListResponse:
    """Справочник целиком или отфильтрованный по подстроке — источник
    значений для ручного выбора (кнопка «Добавить навык»).

    Ищет и по названию, и по алиасам (приложение A справочника):
    «Эксель» должен находить «Microsoft Excel», а не только то, что
    совпадает буквально с каноническим названием.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        skills = await Skill.all().order_by("name").limit(SKILLS_LIST_LIMIT)
        return SkillListResponse(items=[SkillRead.from_skill(skill) for skill in skills])

    name_matches = await Skill.filter(name__icontains=cleaned).values_list(
        "id", flat=True
    )
    alias_matches = await SkillAlias.filter(alias__icontains=cleaned).values_list(
        "skill_id", flat=True
    )
    ids = set(name_matches) | set(alias_matches)
    if not ids:
        return SkillListResponse(items=[])

    skills = await Skill.filter(id__in=ids).order_by("name").limit(SKILLS_LIST_LIMIT)
    return SkillListResponse(items=[SkillRead.from_skill(skill) for skill in skills])


async def validate_skill_ids(skill_ids: list[int]) -> list[int]:
    """Проверяет, что все id существуют в справочнике, иначе `422`.

    Дедупликация — на уровне схемы (`CandidateProfileUpdateRequest`): здесь
    только проверка существования, чтобы не плодить одну и ту же логику в
    двух местах.
    """
    if not skill_ids:
        return []
    existing = set(
        await Skill.filter(id__in=skill_ids).values_list("id", flat=True)
    )
    missing = [skill_id for skill_id in skill_ids if skill_id not in existing]
    if missing:
        raise ValidationError(
            "Один или несколько навыков не найдены в справочнике",
            code="unknown_skill_id",
            details={"skill_ids": missing},
        )
    return skill_ids


async def resolve_skill_names(skill_ids: Iterable[int]) -> dict[int, str]:
    """Пакетно — id -> название, для карточек списком (без запроса на
    каждого кандидата отдельно)."""
    ids = {skill_id for skill_id in skill_ids if skill_id is not None}
    if not ids:
        return {}
    return {
        skill.id: skill.name
        for skill in await Skill.filter(id__in=ids)
    }


def skills_for_profile(
    profile: CandidateProfile | None, names: dict[int, str]
) -> list[SkillRead]:
    """Навыки профиля в читаемом виде. Id, которого больше нет в справочнике
    (данные разошлись), молча пропускается — не должно ронять карточку."""
    if profile is None:
        return []
    return [
        SkillRead(id=skill_id, name=names[skill_id])
        for skill_id in profile.skill_ids or []
        if skill_id in names
    ]


async def suggest_skill_ids(text: str) -> list[int]:
    """Навыки из справочника, упомянутые в тексте резюме (экран C11 UX-карты,
    «Найденные навыки»).

    Простое сопоставление по названию и по алиасам (приложение A
    справочника — «iiko»/«Айко» находят «Работа с iiko Front», даже если в
    резюме не встречается канонический вариант), без ИИ: работает и когда
    ни один ИИ-провайдер не ответил (раздел 57 — недоступность ИИ не должна
    ломать сценарий), и не может предложить то, чего нет в справочнике — в
    отличие от свободного текста, который вернул бы провайдер.
    """
    if not text:
        return []
    haystack = text.casefold()
    matched: set[int] = {
        skill.id
        for skill in await Skill.all().only("id", "name")
        if _mentions(haystack, skill.name.casefold())
    }
    matched.update(
        alias.skill_id
        for alias in await SkillAlias.all().only("alias", "skill_id")
        if _mentions(haystack, alias.alias.casefold())
    )
    return sorted(matched)


def _mentions(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    # Не `\bneedle\b`: `\b` требует ПЕРЕХОДА словарный/несловарный символ на
    # каждом конце needle, а часть названий и алиасов справочника начинается
    # или заканчивается пунктуацией («.NET», «1С:ЗУП», «R-Keeper», «Эксель
    # (тест)» в тесте) — тогда оба соседних символа несловарные, и `\b` там
    # никогда не совпадёт. Явные lookaround проверяют только окружение в
    # haystack, а не то, чем является сам граничный символ needle.
    pattern = rf"(?<!\w){re.escape(needle)}(?!\w)"
    return re.search(pattern, haystack) is not None
