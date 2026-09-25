"""Схема входящего аналитического события с фронта. Раздел 60 тех-доки."""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Раздел 60: события, за которыми нет backend-операции — их может прислать
# только фронт. Остальные события каталога backend пишет сам из бизнес-кода.
AnalyticsEventName = Literal[
    "vacancy_creation_started",
    "vacancy_viewed",
    "vacancy_swiped_left",
    "vacancy_swiped_right",
    "candidate_card_viewed",
    "status_board_opened",
]

MAX_PAYLOAD_KEYS = 10


class AnalyticsEventRequest(BaseModel):
    event_name: AnalyticsEventName
    # Только то, что фронт и так знает про текущий экран (vacancy_id,
    # application_id и т.п.) — без произвольных данных пользователя.
    payload: dict[str, Any] | None = Field(default=None, max_length=MAX_PAYLOAD_KEYS)
