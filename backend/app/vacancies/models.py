"""Вакансия и всё, что к ней привязано. Разделы 15, 16, 18, 24 тех-доки."""

from tortoise import fields
from tortoise.models import Model

from app.core.enums import CriterionType, ScreeningQuestionType, VacancyStatus


class Vacancy(Model):
    """Вакансия работодателя."""

    id = fields.BigIntField(primary_key=True)
    employer = fields.ForeignKeyField(
        "models.User",
        related_name="vacancies",
        on_delete=fields.CASCADE,
    )
    title = fields.CharField(max_length=255)
    location = fields.CharField(max_length=255, null=True)
    salary_min = fields.DecimalField(max_digits=12, decimal_places=2, null=True)
    salary_max = fields.DecimalField(max_digits=12, decimal_places=2, null=True)
    schedule = fields.CharField(max_length=100, null=True)
    status = fields.CharEnumField(
        VacancyStatus, max_length=20, default=VacancyStatus.DRAFT, db_index=True
    )
    # Токен публичной ссылки {APP_URL}/v/{public_token}: генерируется один раз
    # при первой публикации и может быть перевыпущен без создания новой вакансии.
    public_token = fields.CharField(max_length=32, null=True, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "vacancies"
        indexes = (("employer_id",),)

    def __str__(self) -> str:
        return f"Vacancy({self.pk})"


class VacancyCriterion(Model):
    """Формализованный критерий вакансии для hard filters и ranking."""

    id = fields.BigIntField(primary_key=True)
    vacancy = fields.ForeignKeyField(
        "models.Vacancy",
        related_name="criteria",
        on_delete=fields.CASCADE,
    )
    type = fields.CharEnumField(CriterionType, max_length=50)
    required = fields.BooleanField()
    value = fields.JSONField()
    # Вес используется только ranking (P1+); обязательный критерий решается соответствием.
    weight = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "vacancy_criteria"
        indexes = (("vacancy_id",),)


class ScreeningQuestion(Model):
    """Вопрос первичного отбора. В P0 на вакансию приходится 3–4 вопроса."""

    id = fields.BigIntField(primary_key=True)
    vacancy = fields.ForeignKeyField(
        "models.Vacancy",
        related_name="screening_questions",
        on_delete=fields.CASCADE,
    )
    question = fields.TextField()
    type = fields.CharEnumField(ScreeningQuestionType, max_length=50)
    required = fields.BooleanField()
    sort_order = fields.IntField()
    validation_rules = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "screening_questions"
        indexes = (("vacancy_id",),)
        ordering = ["sort_order"]


class ReferralLink(Model):
    """Ссылка для привлечения кандидатов на вакансию. Функционал P2."""

    id = fields.BigIntField(primary_key=True)
    vacancy = fields.ForeignKeyField(
        "models.Vacancy",
        related_name="referral_links",
        on_delete=fields.CASCADE,
    )
    source_user = fields.ForeignKeyField(
        "models.User",
        related_name="referral_links",
        on_delete=fields.CASCADE,
    )
    code = fields.CharField(max_length=100, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "referral_links"
        indexes = (("vacancy_id",),)
