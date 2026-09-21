"""Логирование запросов.

Раздел 77: логируем request id, эндпоинт, код ответа, длительность и user_id,
если он известен. Токены, секрет сессии, cookie и полная initData в логи не попадают.
"""

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.access")


class ContextFilter(logging.Filter):
    """Подмешивает request_id и user_id в каждую запись."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get() or "-"
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] "
            "req=%(request_id)s user=%(user_id)s %(message)s"
        )
    )
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # uvicorn пишет собственный access-лог — он дублирует наш middleware
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error", "tortoise", "aerich"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Присваивает request id, замеряет длительность и пишет строку доступа."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request_id_token = request_id_var.set(request_id)
        user_id_token = user_id_var.set(None)
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self._log(request, 500, started, logging.ERROR)
            raise
        else:
            response.headers[REQUEST_ID_HEADER] = request_id
            self._log(request, response.status_code, started, logging.INFO)
            return response
        finally:
            request_id_var.reset(request_id_token)
            user_id_var.reset(user_id_token)

    def _log(self, request: Request, status_code: int, started: float, level: int) -> None:
        # Зависимость авторизации кладёт user_id в request.state: contextvar,
        # выставленный ниже по стеку, до middleware не доходит.
        user_id_var.set(getattr(request.state, "user_id", None))
        logger.log(
            level,
            "%s %s -> %s за %.1f мс",
            request.method,
            request.url.path,
            status_code,
            (time.perf_counter() - started) * 1000,
        )


def bind_user_id(request: Request, user_id: int | None) -> None:
    """Вызывается зависимостью авторизации, чтобы user_id попал в логи запроса."""
    request.state.user_id = user_id
    user_id_var.set(user_id)
