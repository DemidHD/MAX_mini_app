"""Запись аналитических событий.

Раздел 25: ошибки аналитики не должны ломать основной пользовательский сценарий,
поэтому исключения перехватываются здесь и только логируются.
"""

import logging
from typing import Any

from app.analytics.models import AnalyticsEvent

logger = logging.getLogger("app.analytics")


async def log_event(
    event_name: str,
    *,
    user_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        await AnalyticsEvent.create(
            user_id=user_id, event_name=event_name, payload=payload
        )
    except Exception:  # noqa: BLE001 — аналитика не влияет на сценарий
        logger.warning("Не удалось записать событие %s", event_name, exc_info=True)
