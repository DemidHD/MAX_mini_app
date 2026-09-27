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

    `session_token` дублирует ту же сессию, что уже установлена HTTP-only
    cookie — это fallback для web.max.ru, где Mini App открыт во фрейме и
    cookie с домена backend считается сторонней (браузер её блокирует).
    Frontend отправляет это значение в заголовке `Authorization: Bearer …`,
    когда cookie недоступна; backend принимает сессию из cookie ИЛИ из
    заголовка (раздел 10 тех-доки).
    """

    user: UserRead
    current_step: str
    # Заполняется только для шага `application_status`
    application_id: int | None = None
    session_token: str
