"""Подмены внешних систем для тестов."""

from dataclasses import dataclass, field


@dataclass
class SentMessage:
    """Сообщение, «отправленное» пользователю."""

    user_id: int
    text: str
    deep_link: str | None = None


@dataclass
class RecordingTransport:
    """Транспорт уведомлений, который ничего не отправляет, а запоминает.

    Тесты не должны ходить в MAX Bot API: во-первых, это сеть, во-вторых,
    настоящие сообщения настоящим людям.
    """

    messages: list[SentMessage] = field(default_factory=list)
    # Сколько первых попыток должно завершиться ошибкой: так проверяется
    # повторная отправка (раздел 49)
    fail_first: int = 0
    # Исключение, которым падает отправка
    error: Exception | None = None
    attempts: int = 0

    async def send(
        self, user_id: int, text: str, *, deep_link: str | None = None
    ) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_first:
            raise self.error or RuntimeError("MAX временно недоступен")
        self.messages.append(
            SentMessage(user_id=user_id, text=text, deep_link=deep_link)
        )

    def texts_for(self, user_id: int) -> list[str]:
        return [message.text for message in self.messages if message.user_id == user_id]

    def clear(self) -> None:
        self.messages.clear()
        self.attempts = 0


@dataclass
class FailingTransport:
    """Транспорт, который всегда падает: проверка раздела 47."""

    error: Exception = field(default_factory=lambda: RuntimeError("MAX недоступен"))
    attempts: int = 0

    async def send(
        self, user_id: int, text: str, *, deep_link: str | None = None
    ) -> None:
        self.attempts += 1
        raise self.error
