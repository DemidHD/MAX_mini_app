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
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "candidate_profiles"

    def __str__(self) -> str:
        return f"CandidateProfile({self.pk})"
