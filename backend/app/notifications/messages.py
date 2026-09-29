"""Тексты уведомлений и путь в Mini App для кнопки «Открыть детали». Раздел 46
тех-доки.

Раздел 44 требует, чтобы текст формировал сервис уведомлений, а не каждый
endpoint по-своему. Поэтому все формулировки живут здесь.

До этого файла в тексте была голая https-ссылка `APP_URL + путь` — открытая
не из MAX (например, тапом по ссылке в сообщении бота), она вела в системный
браузер без `window.WebApp.initData`, и пользователь попадал на экран ошибки
авторизации вместо конкретного экрана (баг демо). Поэтому `NotificationContent`
отдаёт путь отдельно от текста: `app.bot.keyboard` строит из него кнопку,
которая открывает Mini App по-настоящему (`OpenAppButton`, `maxapi`), а не
браузер. Путь — маршрут frontend (`frontend/src/app/routes.ts`), без
`APP_URL`: он не глобальный URL, а `start_param` при открытии Mini App.
"""

import logging
from dataclasses import dataclass
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


@dataclass(frozen=True)
class NotificationContent:
    """Текст уведомления и путь для кнопки «Открыть детали» под ним."""

    text: str
    path: str


def employer_home_path() -> str:
    """Кабинет работодателя — только когда нет конкретной сущности."""
    return "/employer"


def application_path(application_id: int) -> str:
    """Экран отклика кандидата: статус, слоты, назначенное собеседование."""
    return f"/candidate/applications/{application_id}"


def employer_application_path(application_id: int) -> str:
    """Карточка кандидата у работодателя — конкретный отклик, а не кабинет.

    UX-карта требует открывать именно сущность события (раздел «Данные:
    application_id»), а не главную: раньше все уведомления работодателю вели
    на `employer_home_path()`, хотя `application_id` уже был известен.
    """
    return f"/employer/applications/{application_id}"


def application_created(*, vacancy_title: str, application_id: int) -> NotificationContent:
    return NotificationContent(
        text=f"Новый отклик на вакансию «{vacancy_title}».",
        path=employer_application_path(application_id),
    )


def candidate_invited(*, vacancy_title: str, application_id: int) -> NotificationContent:
    return NotificationContent(
        text=f"Вас пригласили на собеседование по вакансии «{vacancy_title}».",
        path=application_path(application_id),
    )


def application_reserved(*, vacancy_title: str, application_id: int) -> NotificationContent:
    return NotificationContent(
        text=(
            f"Работодатель сохранил ваш отклик на вакансию «{vacancy_title}» "
            "в резерве и может вернуться к решению позже."
        ),
        path=application_path(application_id),
    )


def application_rejected(*, vacancy_title: str, application_id: int) -> NotificationContent:
    """Функции 27-28 UX-карты: нейтральное сообщение, без оценки кандидата —
    только факт решения по объективным условиям вакансии."""
    return NotificationContent(
        text=(
            f"По вакансии «{vacancy_title}» отклик не подошёл по текущим "
            "условиям. Спасибо за интерес — другие вакансии доступны в ленте."
        ),
        path=application_path(application_id),
    )


def mutual_interest_for_candidate(
    *, vacancy_title: str, application_id: int
) -> NotificationContent:
    return NotificationContent(
        text=(
            f"Взаимный интерес по вакансии «{vacancy_title}». "
            "Осталось выбрать время собеседования."
        ),
        path=application_path(application_id),
    )


def mutual_interest_for_employer(
    *, vacancy_title: str, application_id: int
) -> NotificationContent:
    return NotificationContent(
        text=(
            f"Взаимный интерес по вакансии «{vacancy_title}». "
            "Предложите кандидату время собеседования."
        ),
        path=employer_application_path(application_id),
    )


def interview_slot_available(
    *, vacancy_title: str, application_id: int
) -> NotificationContent:
    return NotificationContent(
        text=f"Работодатель предложил время собеседования по вакансии «{vacancy_title}».",
        path=application_path(application_id),
    )


def interview_booked_for_candidate(
    *, vacancy_title: str, starts_at: datetime, application_id: int
) -> NotificationContent:
    return NotificationContent(
        text=(
            f"Собеседование по вакансии «{vacancy_title}» назначено на "
            f"{format_moment(starts_at)}."
        ),
        path=application_path(application_id),
    )


def interview_booked_for_employer(
    *, vacancy_title: str, starts_at: datetime, application_id: int
) -> NotificationContent:
    return NotificationContent(
        text=(
            f"Кандидат выбрал время собеседования по вакансии «{vacancy_title}»: "
            f"{format_moment(starts_at)}."
        ),
        path=employer_application_path(application_id),
    )


def bot_greeting() -> str:
    """Ответ бота на `/start` и на открытие диалога (раздел 43)."""
    return (
        "👋 ДОБРО ПОЖАЛОВАТЬ!\n"
        "\n"
        "Вам не кажется, это МЭТЧ 👉👈\n"
        "\n"
        "Наша платформа — место, где работа находит людей, а люди находят "
        "работу ✨\n"
        "\n"
        "🧑‍💼 В ПОИСКАХ СОТРУДНИКА?\n"
        "Опишите, кто нужен и мы соберём вакансию за вас, а отклики придут "
        "прямо сюда, в MAX\n"
        "\n"
        "🔎 ИЩЕТЕ РАБОТУ?\n"
        "Выбирайте подходящие вакансии и откликайтесь по свайпам\n"
        "\n"
        "🗓 Назначайте собеседование прямо здесь в один клик\n"
        "\n"
        "Ну что, заМЭТЧимся? 👇"
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
