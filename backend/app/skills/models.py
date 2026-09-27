"""Справочник навыков кандидата. Не из тех-доки — продуктовое решение.

Единый источник значений для `candidate_profiles.skill_ids`: кандидат
выбирает id отсюда, а не вписывает произвольный текст — иначе в базе
множились бы дубли вроде «Excel» / «MS Excel» / «Эксель».

Данные — «MAX Найм | Справочник навыков v1.0» (2166 канонических навыков в
37 категориях, 66 примеров алиасов; 16 позиций с одинаковым названием в
разных категориях источника схлопнуты в одну запись — раздел 4 самого
справочника требует «один смысл — один канонический навык», см.
`app.skills.seed`). Загружается `scripts/seed_skills.py` из
`app/skills/data/skills.json` и `aliases.json`, а не хранится в коде.
"""

from tortoise import fields
from tortoise.models import Model


class Skill(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)
    # Внешний код исходного справочника (например «SK-01-001»). Nullable —
    # навык, заведённый вручную мимо загрузчика, кода может не иметь.
    code = fields.CharField(max_length=20, unique=True, null=True)
    # Категория из справочника (например «Кофе, бар и напитки») — плоской
    # строкой, без отдельной таблицы категорий: для MVP-масштаба (37 штук,
    # только для отображения/группировки) это не требует нормализации.
    category = fields.CharField(max_length=150, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "skills"

    def __str__(self) -> str:
        return f"Skill({self.id}, {self.name!r})"


class SkillAlias(Model):
    """Разговорный/сокращённый вариант ввода, ведущий к каноническому навыку
    (приложение A справочника — «Эксель»/«Excel» -> «Microsoft Excel»).
    Используется поиском (`GET /api/skills?query=`) и подсказкой из резюме
    (`app.skills.service.suggest_skill_ids`), чтобы находить навык и по
    неканоническому названию."""

    id = fields.IntField(primary_key=True)
    alias = fields.CharField(max_length=150, unique=True)
    skill = fields.ForeignKeyField(
        "models.Skill", related_name="aliases", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "skill_aliases"

    def __str__(self) -> str:
        return f"SkillAlias({self.alias!r} -> {self.skill_id})"
