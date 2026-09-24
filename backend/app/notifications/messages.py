"""Тексты уведомлений и ссылки в Mini App. Раздел 46 тех-доки.

Раздел 44 требует, чтобы текст формировал сервис уведомлений, а не каждый
endpoint по-своему. Поэтому все формулировки живут здесь.

Ссылки собираются из `APP_URL` и маршрутов Mini App (`frontend/src/app/routes.ts`).
Набор маршрутов — общий контракт с frontend: если там путь поменяется,
поменять нужно и здесь.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

logger = logging.getLogger("app.notifications")

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def employer_home_url() -> str:
    """Кабинет работодателя."""
    return _url("/employer")


def application_url(application_id: int) -> str:
    """Экран отклика кандидата: статус, слоты, назначенное собеседование."""
    return _url(f"/candidate/applications/{application_id}")


def application_created(*, vacancy_title: str) -> str:
    return (
        f"Новый отклик на вакансию «{vacancy_title}».\n"
        f"Посмотреть кандидата: {employer_home_url()}"
    )


def candidate_invited(*, vacancy_title: str, application_id: int) -> str:
    return (
        f"Вас пригласили на собеседование по вакансии «{vacancy_title}».\n"
        f"Открыть отклик: {application_url(application_id)}"
    )


def application_reserved(*, vacancy_title: str, application_id: int) -> str:
    return (
        f"Работодатель сохранил ваш отклик на вакансию «{vacancy_title}» "
        "в резерве и может вернуться к решению позже.\n"
        f"Открыть отклик: {application_url(application_id)}"
    )


def mutual_interest_for_candidate(*, vacancy_title: str, application_id: int) -> str:
    return (
        f"Взаимный интерес по вакансии «{vacancy_title}». "
        "Осталось выбрать время собеседования.\n"
        f"Выбрать время: {application_url(application_id)}"
    )


def mutual_interest_for_employer(*, vacancy_title: str) -> str:
    return (
        f"Взаимный интерес по вакансии «{vacancy_title}». "
        "Предложите кандидату время собеседования.\n"
        f"Открыть вакансию: {employer_home_url()}"
    )


def interview_slot_available(*, vacancy_title: str, application_id: int) -> str:
    return (
        f"Работодатель предложил время собеседования по вакансии «{vacancy_title}».\n"
        f"Выбрать время: {application_url(application_id)}"
    )


def interview_booked_for_candidate(
    *, vacancy_title: str, starts_at: datetime, application_id: int
) -> str:
    return (
        f"Собеседование по вакансии «{vacancy_title}» назначено на "
        f"{format_moment(starts_at)}.\n"
        f"Детали: {application_url(application_id)}"
    )


def interview_booked_for_employer(
    *, vacancy_title: str, starts_at: datetime
) -> str:
    return (
        f"Кандидат выбрал время собеседования по вакансии «{vacancy_title}»: "
        f"{format_moment(starts_at)}.\n"
        f"Детали: {employer_home_url()}"
    )


def bot_greeting() -> str:
    """Ответ бота на `/start` и на открытие диалога (раздел 43)."""
    return (
        "MAX Найм помогает нанять сотрудника и пройти путь до назначенного "
        "собеседования.\n"
        f"Открыть приложение: {_url('/')}"
    )


def format_moment(moment: datetime) -> str:
    """Время в часовом поясе пользователя продукта.

    Хранится всё в UTC, но «14:00 UTC» владельцу кофейни в Москве ничего не
    говорит. Пояс задаётся настройкой `NOTIFICATION_TIMEZONE`.
    """
    zone_name = settings.notification_timezone
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        # Неизвестный пояс — не повод не отправить уведомление
        logger.warning("Неизвестный часовой пояс уведомлений: %s", zone_name)
        zone = ZoneInfo("UTC")
        zone_name = "UTC"

    local = moment.astimezone(zone)
    label = "МСК" if zone_name == "Europe/Moscow" else zone_name
    month = MONTHS_GENITIVE[local.month - 1]
    return f"{local.day} {month}, {local:%H:%M} ({label})"


def _url(path: str) -> str:
    return f"{settings.app_url.rstrip('/')}{path}"
