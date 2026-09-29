"""Демо-вакансии для нагрузки и показа ленты: создаёт N опубликованных
вакансий HoReCa по Москве прямо в той базе, к которой подключён backend.

Вакансии принадлежат отдельному демо-работодателю (`DEMO_EMPLOYER_ID`, не
пользователь MAX), поэтому их легко отличить и удалить целиком, не задев
настоящие данные. Форма критериев и вопросов отбора — та же, что собирает
frontend (`buildVacancyFields`), и формат `api-contracts.md`, «Формат
vacancy_criteria.value»: подбор ленты понимает их как обычные вакансии.

Идемпотентно: считает уже созданные демо-вакансии и досоздаёт только
недостающие до N — повторный запуск и перезапуск контейнера дублей не дают.

Запуск (в контейнере backend, где есть доступ к базе):
    python scripts/seed_demo_vacancies.py                 # 1000 вакансий
    python scripts/seed_demo_vacancies.py --count 300
    python scripts/seed_demo_vacancies.py --delete        # убрать все демо-вакансии

Без консоли (например, на хостинге без exec): задать переменную окружения
`SEED_DEMO_VACANCIES=1000` и перезапустить backend — скрипт с `--from-env`
вызывается при старте (docker-compose.yml) и без переменной ничего не делает.
`SEED_DEMO_VACANCIES=delete` при старте удаляет все демо-вакансии.
"""

import argparse
import asyncio
import os
import random
import secrets
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

# Скрипт запускается как файл, поэтому корень проекта нужно добавить руками
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import cache  # noqa: E402
from app.core.database import TORTOISE_ORM  # noqa: E402
from app.core.enums import (  # noqa: E402
    CriterionType,
    ScreeningQuestionType,
    UserRole,
    VacancyStatus,
)
from app.matching.service import invalidate_feed_pool  # noqa: E402
from app.users.models import User  # noqa: E402
from app.vacancies import images  # noqa: E402
from app.vacancies.models import ScreeningQuestion, Vacancy, VacancyCriterion  # noqa: E402

# Вне диапазона реальных ID пользователей MAX: авторизоваться под ним нельзя
DEMO_EMPLOYER_ID = 9_000_000_000_001
DEFAULT_COUNT = 1000
BATCH_SIZE = 100

# Те же варианты, что у работодателя в форме (frontend, `SCHEDULE_OPTIONS`)
SCHEDULES = ["2/2", "5/2", "Полный день", "Гибкий график"]

# Должность → (зарплата от, до) в рублях и минимальный опыт в месяцах
ROLES: dict[str, tuple[int, int, int]] = {
    "Бариста": (60_000, 90_000, 0),
    "Старший бариста": (80_000, 110_000, 12),
    "Официант": (55_000, 90_000, 0),
    "Бармен": (70_000, 110_000, 6),
    "Повар горячего цеха": (80_000, 130_000, 12),
    "Повар холодного цеха": (75_000, 120_000, 6),
    "Повар-кондитер": (80_000, 125_000, 12),
    "Пекарь": (70_000, 105_000, 6),
    "Су-шеф": (110_000, 160_000, 24),
    "Администратор зала": (80_000, 120_000, 12),
    "Хостес": (50_000, 75_000, 0),
    "Кассир": (55_000, 80_000, 0),
    "Посудомойщица": (45_000, 65_000, 0),
    "Уборщица": (45_000, 60_000, 0),
    "Курьер": (60_000, 100_000, 0),
    "Сомелье": (90_000, 140_000, 24),
    "Кальянщик": (60_000, 100_000, 6),
    "Менеджер кофейни": (90_000, 130_000, 18),
}

COMPANY_KINDS = ["Кофейня", "Ресторан", "Кафе", "Бистро", "Пекарня", "Бар", "Гастробар", "Пиццерия"]
COMPANY_NAMES = [
    "Mokka", "Forma", "Studio 21", "Зерно", "Уют", "Базилик", "Самовар", "Brew Lab",
    "Корица", "Пряности", "Old Town", "Terrassa", "Фасоль", "Лаванда", "Espresso Point",
    "Крошка", "Маяк", "Сезоны", "Ягода", "Шафран", "Nord", "Oliva", "Тесто", "Облака",
]
METRO = [
    "Белорусская", "Тверская", "Пушкинская", "Чистые пруды", "Курская", "Павелецкая",
    "Таганская", "Октябрьская", "Парк культуры", "Киевская", "Смоленская", "Арбатская",
    "Маяковская", "Новослободская", "Сокол", "Динамо", "Бауманская", "Лубянка",
    "Проспект Мира", "Сухаревская", "Китай-город", "Третьяковская", "Фрунзенская", "Аэропорт",
]
DESCRIPTIONS = [
    "Дружная команда, бесплатное питание в смену, официальное оформление.",
    "Обучение с нуля, стабильная выплата два раза в месяц, скидка на меню.",
    "Уютное заведение в центре, гибкий график, чаевые делим честно.",
    "Форма за счёт компании, премии по итогам месяца, рост до старшей позиции.",
]


def _build_vacancy(rng: random.Random, today: date) -> dict:
    """Одна вакансия: поля, критерии и вопросы отбора в формате frontend."""
    title = rng.choice(list(ROLES))
    salary_low, salary_high, min_months = ROLES[title]
    step = 5_000
    salary_min = rng.randrange(salary_low, salary_high - step + 1, step)
    salary_max = rng.randrange(salary_min + step, salary_high + step * 2 + 1, step)
    schedule = rng.choice(SCHEDULES)
    available_from = today + timedelta(days=rng.choice([3, 7, 14, 30]))

    required = {
        CriterionType.LOCATION: True,
        CriterionType.SCHEDULE: rng.random() < 0.5,
        CriterionType.SALARY: rng.random() < 0.3,
        CriterionType.EXPERIENCE: min_months > 0 and rng.random() < 0.4,
        CriterionType.AVAILABLE_FROM: rng.random() < 0.2,
    }
    criteria = [
        (CriterionType.LOCATION, {"city": "Москва"}),
        (CriterionType.SCHEDULE, {"schedule": schedule}),
        (CriterionType.SALARY, {"max": salary_max}),
        (CriterionType.EXPERIENCE, {"min_months": min_months}),
        (CriterionType.AVAILABLE_FROM, {"date": available_from.isoformat()}),
    ]

    # Как `buildScreeningQuestions`: отсекающие вопросы по обязательным условиям
    questions = []
    if required[CriterionType.SCHEDULE]:
        questions.append(f"Сможете работать по графику {schedule}?")
    if required[CriterionType.AVAILABLE_FROM]:
        questions.append(f"Готовы выйти на работу до {available_from.strftime('%d.%m')}?")

    return {
        "title": title,
        "company_name": f"{rng.choice(COMPANY_KINDS)} {rng.choice(COMPANY_NAMES)}",
        "description": rng.choice(DESCRIPTIONS),
        "location": f"Москва, м. {rng.choice(METRO)}",
        "salary_min": Decimal(salary_min),
        "salary_max": Decimal(salary_max),
        "schedule": schedule,
        "criteria": [(kind, required[kind], value) for kind, value in criteria],
        "questions": questions,
    }


async def _demo_employer() -> User:
    employer, _ = await User.get_or_create(
        user_id=DEMO_EMPLOYER_ID,
        defaults={"first_name": "Демо-работодатель", "role": UserRole.EMPLOYER},
    )
    return employer


async def _image_urls(titles: list[str]) -> dict[str, list[str]]:
    """По несколько фото на должность: 1000 запросов к Openverse не нужны,
    а одинаковое фото у всех баристов выглядело бы странно."""
    found = await asyncio.gather(*(images.find_image(title) for title in titles for _ in range(3)))
    urls = {
        title: list(dict.fromkeys(url for url in found[index * 3 : index * 3 + 3] if url))
        for index, title in enumerate(titles)
    }
    print(f"Фото найдено для {sum(1 for value in urls.values() if value)} из {len(titles)} должностей")
    return urls


async def seed(count: int, with_images: bool) -> None:
    employer = await _demo_employer()
    existing = await Vacancy.filter(employer_id=employer.user_id).count()
    missing = count - existing
    if missing <= 0:
        print(f"Демо-вакансий уже {existing} — досоздавать нечего")
        return

    print(f"Демо-вакансий сейчас {existing}, создаю ещё {missing}")
    # Сдвиг по уже созданным — повторный запуск не повторяет те же вакансии
    rng = random.Random(20260929 + existing)
    today = date.today()
    photos = await _image_urls(list(ROLES)) if with_images else {}

    created = 0
    while created < missing:
        batch = [_build_vacancy(rng, today) for _ in range(min(BATCH_SIZE, missing - created))]
        async with in_transaction() as connection:
            for data in batch:
                options = photos.get(data["title"])
                vacancy = await Vacancy.create(
                    employer_id=employer.user_id,
                    title=data["title"],
                    company_name=data["company_name"],
                    description=data["description"],
                    location=data["location"],
                    salary_min=data["salary_min"],
                    salary_max=data["salary_max"],
                    schedule=data["schedule"],
                    image_url=rng.choice(options) if options else None,
                    status=VacancyStatus.PUBLISHED,
                    public_token=secrets.token_urlsafe(24),
                    using_db=connection,
                )
                await VacancyCriterion.bulk_create(
                    [
                        VacancyCriterion(vacancy_id=vacancy.id, type=kind, required=is_required, value=value)
                        for kind, is_required, value in data["criteria"]
                    ],
                    using_db=connection,
                )
                if data["questions"]:
                    await ScreeningQuestion.bulk_create(
                        [
                            ScreeningQuestion(
                                vacancy_id=vacancy.id,
                                question=question,
                                type=ScreeningQuestionType.BOOLEAN,
                                required=True,
                                sort_order=index,
                                validation_rules={"must_equal": True},
                            )
                            for index, question in enumerate(data["questions"], start=1)
                        ],
                        using_db=connection,
                    )
        created += len(batch)
        print(f"  создано {created}/{missing}")

    await invalidate_feed_pool()
    print(f"Готово: демо-вакансий {existing + created}")


async def delete() -> None:
    """Удаляет демо-работодателя; вакансии, критерии, вопросы и отклики на
    них уходят каскадом (`on_delete=CASCADE`)."""
    removed = await Vacancy.filter(employer_id=DEMO_EMPLOYER_ID).count()
    await User.filter(user_id=DEMO_EMPLOYER_ID).delete()
    await invalidate_feed_pool()
    print(f"Удалено демо-вакансий: {removed}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="сколько демо-вакансий должно быть в итоге")
    parser.add_argument("--delete", action="store_true", help="удалить все демо-вакансии")
    parser.add_argument("--no-images", action="store_true", help="не искать фото в Openverse")
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="взять количество (или delete) из SEED_DEMO_VACANCIES; без переменной ничего не делать",
    )
    args = parser.parse_args()

    count = args.count
    remove = args.delete
    if args.from_env:
        raw = os.environ.get("SEED_DEMO_VACANCIES", "").strip().lower()
        if not raw or raw == "0":
            return
        if raw == "delete":
            remove = True
        else:
            count = int(raw)

    await Tortoise.init(config=TORTOISE_ORM)
    await cache.connect()
    try:
        if remove:
            await delete()
        else:
            await seed(count, with_images=not args.no_images)
    finally:
        await cache.disconnect()
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
