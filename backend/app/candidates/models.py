"""Профиль кандидата. Раздел 14 тех-доки."""

from tortoise import fields
from tortoise.models import Model
from tortoise.validators import MinValueValidator


class CandidateProfile(Model):
    """Профиль кандидата, используемый для подбора вакансий. Связь с User — 1:1."""

    user = fields.OneToOneField(
        "models.User",
        primary_key=True,
        related_name="candidate_profile",
        on_delete=fields.CASCADE,
    )
    desired_role = fields.CharField(max_length=255)
    city = fields.CharField(max_length=255, null=True)
    salary = fields.DecimalField(max_digits=12, decimal_places=2, null=True)
    schedule = fields.CharField(max_length=100, null=True)
    experience_months = fields.IntField(null=True, validators=[MinValueValidator(0)])
    available_from = fields.DateField(null=True)
    # Функция 29 UX-карты (экран C11): PDF/DOCX резюме, необязательное.
    # Раздел 3 тех-доки — бинарник в `storage/resumes/{user_id}/...`, в БД
    # только путь. `resume_text` — извлечённый текст: используется разбором
    # (`POST /candidate/resume/parse`) без повторного чтения файла с диска.
    resume_path = fields.CharField(max_length=500, null=True)
    resume_text = fields.TextField(null=True)
    resume_updated_at = fields.DatetimeField(null=True)
    # Не из тех-доки — продуктовое решение. Хранит id из справочника
    # `skills` (`app.skills`), а не свободный текст — иначе множились бы
    # дубли вроде «Excel»/«MS Excel». `null=True`, а не пустой список по
    # умолчанию: тот же приём, что и у остальных JSON-колонок в проекте
    # (`VacancyCriterion.value` и т.п.) — приложение везде читает как
    # `skill_ids or []`, а не полагается на DB DEFAULT.
    skill_ids = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "candidate_profiles"

    def __str__(self) -> str:
        return f"CandidateProfile({self.pk})"
