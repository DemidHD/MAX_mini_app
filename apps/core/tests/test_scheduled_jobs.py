"""Шаг 8: то, что делают фоновые задачи (тех. ТЗ 4).

Проверяются функции сервисного слоя, а не обёртки Celery: обёртка — три строки
поверх них, а вся логика и требование идемпотентности живут здесь.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from navigator.config import Settings
from navigator.domains.food import service as food
from navigator.domains.gamification import service as gamification
from navigator.domains.gamification.models import PointsTransaction
from navigator.domains.notifications import service as notifications
from navigator.domains.schedule import service as schedule
from navigator.domains.tracker import service as tracker
from navigator.domains.users import service as users
from navigator.domains.vuz_selection import service as vuz_selection
from tests.conftest import as_user

pytestmark = pytest.mark.integration


async def student(who: str, university: users.University) -> users.User:
    user = await users.get_or_create(who)
    await users.update_profile(user, status=users.UserStatus.student, university_id=university.id)
    return user


async def feed_of(client: httpx.AsyncClient, who: str = "u-1") -> list[dict[str, object]]:
    response = await client.get("/api/v1/notifications", headers=as_user(who))
    assert response.status_code == 200
    items: list[dict[str, object]] = response.json()["items"]
    return items


class TestAdmissionReminders:
    async def test_reminder_goes_out_seven_days_before(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """ТЗ 3.7: за 7 дней и за 1 день до окончания приёма."""
        await users.sync_universities()
        university = (await users.list_universities())[0]
        assert university.admission_deadline is not None
        user = await users.get_or_create("u-1")
        await vuz_selection.track_university(user, university.id)

        report = await tracker.admission_reminders(
            integration_settings, today=university.admission_deadline - timedelta(days=7)
        )

        assert report.sent == 1
        assert (await feed_of(api_client))[0]["kind"] == "admission_start"

    async def test_reminder_is_not_sent_on_other_days(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        university = (await users.list_universities())[0]
        assert university.admission_deadline is not None
        user = await users.get_or_create("u-1")
        await vuz_selection.track_university(user, university.id)

        report = await tracker.admission_reminders(
            integration_settings, today=university.admission_deadline - timedelta(days=5)
        )

        assert report.sent == 0

    async def test_second_run_the_same_day_sends_nothing(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """Тех. ТЗ 4: повторный запуск не создаёт дублей."""
        await users.sync_universities()
        university = (await users.list_universities())[0]
        assert university.admission_deadline is not None
        user = await users.get_or_create("u-1")
        await vuz_selection.track_university(user, university.id)
        day = university.admission_deadline - timedelta(days=1)
        await tracker.admission_reminders(integration_settings, today=day)

        report = await tracker.admission_reminders(integration_settings, today=day)

        assert report.sent == 0
        assert len(await feed_of(api_client)) == 1


class TestPositionSync:
    async def test_movement_produces_a_notification(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """ТЗ 3.6: «поднялись с X на Y» — это и есть смысл блока."""
        await users.sync_universities()
        university = (await users.list_universities())[0]
        user = await users.get_or_create("u-1")
        await vuz_selection.track_university(user, university.id)
        await tracker.record_position(user, university.id, 200)

        report = await tracker.sync_positions(integration_settings)

        assert report.moved == 1
        item = (await feed_of(api_client))[0]
        assert item["kind"] == "position_changed"
        assert "200" in str(item["body"])

    async def test_second_run_does_not_duplicate_the_notification(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        university = (await users.list_universities())[0]
        user = await users.get_or_create("u-1")
        await vuz_selection.track_university(user, university.id)
        await tracker.record_position(user, university.id, 1)

        await tracker.sync_positions(integration_settings)
        await tracker.sync_positions(integration_settings)

        assert await feed_of(api_client) == []


def schedule_today() -> date:
    """Сегодня по часам расписания, а не по часам раннера.

    `date.today()` здесь читался бы естественно и был бы неверен: сервис
    считает дату по Москве, и с 21:00 UTC до полуночи «завтра» у теста и
    «завтра» у сервиса — разные дни. Тесты падали именно в это окно, каждый
    день по три часа.

    Дату нельзя просто прибить константой: `add_deadline` сверяет её
    с настоящими часами и отвергает прошедшую.
    """
    return datetime.now(schedule.SCHEDULE_TIMEZONE).date()


class TestDeadlineReminders:
    async def test_reminder_a_day_before(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """ТЗ 4.6: напоминание о личном дедлайне за сутки."""
        await users.sync_universities()
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        # День фиксируется один раз и передаётся задаче явно — так же, как
        # в остальных тестах файла. Иначе тест и задача берут «сегодня»
        # каждый свой, и результат зависит от часа прогона.
        day = schedule_today()
        await schedule.add_deadline(user, "Курсовая", day + timedelta(days=1))

        report = await schedule.deadline_reminders(integration_settings, today=day)

        assert report.sent == 1
        assert (await feed_of(api_client))[0]["kind"] == "deadline_soon"

    async def test_far_deadline_is_silent(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        day = schedule_today()
        await schedule.add_deadline(user, "Отчёт", day + timedelta(days=9))

        report = await schedule.deadline_reminders(integration_settings, today=day)

        assert report.sent == 0

    async def test_second_run_sends_nothing(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        day = schedule_today()
        await schedule.add_deadline(user, "Курсовая", day + timedelta(days=1))
        await schedule.deadline_reminders(integration_settings, today=day)

        report = await schedule.deadline_reminders(integration_settings, today=day)

        assert report.sent == 0
        assert len(await feed_of(api_client)) == 1


class TestScheduleDigest:
    async def test_digest_goes_out_at_the_users_hour(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """ТЗ 4.4 и уточнение У9: час у каждого свой."""
        await users.sync_universities()
        await schedule.sync_timetables(integration_settings)
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        await schedule.bind_group(user, "ИС-231")
        await notifications.update_settings(user, digest_hour=8)

        moment = datetime(2026, 8, 17, 8, 5, tzinfo=schedule.SCHEDULE_TIMEZONE)
        report = await schedule.send_digests(integration_settings, now=moment)

        assert report.sent == 1
        assert (await feed_of(api_client))[0]["kind"] == "schedule_digest"

    async def test_no_digest_at_another_hour(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        await schedule.sync_timetables(integration_settings)
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        await schedule.bind_group(user, "ИС-231")
        await notifications.update_settings(user, digest_hour=19)

        moment = datetime(2026, 8, 17, 8, 5, tzinfo=schedule.SCHEDULE_TIMEZONE)

        assert (await schedule.send_digests(integration_settings, now=moment)).sent == 0

    async def test_applicant_gets_no_digest(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """Раздел закрыт статусом — рассылка тоже (ТЗ 4.2)."""
        await users.sync_universities()
        await schedule.sync_timetables(integration_settings)
        await users.get_or_create("u-1")

        moment = datetime(2026, 8, 17, 8, 5, tzinfo=schedule.SCHEDULE_TIMEZONE)

        assert (await schedule.send_digests(integration_settings, now=moment)).sent == 0

    async def test_second_run_the_same_day_sends_nothing(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()
        await schedule.sync_timetables(integration_settings)
        university = (await users.list_universities())[0]
        user = await student("u-1", university)
        await schedule.bind_group(user, "ИС-231")
        moment = datetime(2026, 8, 17, 8, 5, tzinfo=schedule.SCHEDULE_TIMEZONE)
        await schedule.send_digests(integration_settings, now=moment)

        report = await schedule.send_digests(integration_settings, now=moment)

        assert report.sent == 0


class TestMonthlyTitleJob:
    async def test_winner_is_congratulated(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        """ТЗ 6.6: персональное уведомление-поздравление."""
        user = await users.get_or_create("u-1")
        await users.add_points(user, 300)
        row = await PointsTransaction.create(
            user_id=user.id,
            amount=300,
            reason=gamification.PointsReason.career_test,
            subject="last-month",
        )
        row.created_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
        await row.save(update_fields=["created_at"])

        title = await gamification.award_monthly_title(
            integration_settings, now=datetime(2026, 8, 1, 3, tzinfo=UTC)
        )

        assert title is not None
        assert (await feed_of(api_client))[0]["kind"] == "monthly_title"

    async def test_second_run_does_not_congratulate_twice(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        user = await users.get_or_create("u-1")
        await users.add_points(user, 300)
        row = await PointsTransaction.create(
            user_id=user.id,
            amount=300,
            reason=gamification.PointsReason.career_test,
            subject="last-month",
        )
        row.created_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
        await row.save(update_fields=["created_at"])
        now = datetime(2026, 8, 1, 3, tzinfo=UTC)
        await gamification.award_monthly_title(integration_settings, now=now)

        await gamification.award_monthly_title(integration_settings, now=now)

        assert len(await feed_of(api_client)) == 1


class TestCacheJobs:
    async def test_food_refresh_is_idempotent(
        self, api_client: httpx.AsyncClient, integration_settings: Settings
    ) -> None:
        await users.sync_universities()

        first = await food.refresh_all(integration_settings)
        second = await food.refresh_all(integration_settings)

        assert first == second
        assert await food.FoodSpotCache.all().count() == second.spots
