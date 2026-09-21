"""Схемы авторизации. Раздел 7 тех-доки."""

from pydantic import BaseModel, Field

from app.users.schemas import UserRead


class AuthMaxRequest(BaseModel):
    """`init_data` — исходная строка `window.WebApp.initData` без пересборки."""

    init_data: str = Field(min_length=1)


class AuthMaxResponse(BaseModel):
    """Ответ авторизации.

    `current_step` нужен frontend, чтобы вернуть пользователя на актуальный шаг
    сценария, а не на стартовый экран. Точный набор значений фиксируется
    совместно с frontend.
    """

    user: UserRead
    current_step: str
    # Заполняется только для шага `application_status`
    application_id: int | None = None
