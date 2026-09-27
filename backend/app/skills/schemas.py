"""Схемы справочника навыков. Не из тех-доки."""

from pydantic import BaseModel, ConfigDict

from app.skills.models import Skill


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    # Категория справочника (например «Кофе, бар и напитки») — для
    # группировки в UI поиска; в карточке кандидата не обязательна к показу.
    category: str | None = None

    @classmethod
    def from_skill(cls, skill: Skill) -> "SkillRead":
        return cls(id=skill.id, name=skill.name, category=skill.category)


class SkillListResponse(BaseModel):
    items: list[SkillRead]
