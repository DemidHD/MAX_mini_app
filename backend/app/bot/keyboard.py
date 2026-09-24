"""Кнопка «Открыть детали» под сообщениями бота (не из тех-доки — исправление
бага демо: обычная https-ссылка `APP_URL + путь` открывалась в системном
браузере, а не в MAX, и там нет `window.WebApp.initData` — пользователь
попадал на экран ошибки авторизации вместо конкретного экрана.

`OpenAppButton.payload` — то же самое, что `start_param` в
`window.WebApp.initDataUnsafe` на стороне Mini App (dev.max.ru/docs/webapps/bridge):
путь внутри приложения, на который нужно перейти после открытия.
"""

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from maxapi.types.attachments import Attachment

logger = logging.getLogger("app.bot")

# Раздел UX-карты, макет B01: карточка уведомления с кнопкой «Открыть детали».
_ENTITY_BUTTON_TEXT = "Открыть детали"
_ROOT_BUTTON_TEXT = "Открыть приложение"


def open_app_attachment(path: str | None) -> "list[Attachment] | None":
    """Вложение с кнопкой, открывающей Mini App (а не браузер).

    `path` — путь внутри Mini App (например, `/employer/applications/42`),
    передаётся в `start_param`; `None` — открыть приложение с корня, для
    событий без конкретной сущности (например, приветствие бота).

    `None` в ответе — бот не настроен на конкретный username
    (`MAX_BOT_USERNAME` пуст): без него `OpenAppButton.web_app` нечем
    заполнить, и сообщение уходит без кнопки, как раньше.
    """
    if not settings.max_bot_username:
        logger.warning(
            "MAX_BOT_USERNAME не задан: сообщение уйдёт без кнопки открытия Mini App"
        )
        return None

    from maxapi.enums.attachment import AttachmentType
    from maxapi.types.attachments import AttachmentButton, ButtonsPayload, OpenAppButton

    button = OpenAppButton(
        text=_ENTITY_BUTTON_TEXT if path else _ROOT_BUTTON_TEXT,
        web_app=settings.max_bot_username,
        payload=path,
    )
    return [
        AttachmentButton(
            type=AttachmentType.INLINE_KEYBOARD,
            payload=ButtonsPayload(buttons=[[button]]),
        )
    ]
