"""Redis-кэш часто читаемых и редко меняющихся данных. Раздел 72 тех-доки
относит Redis к опциональной инфраструктуре («только при фактической
необходимости» — среди прочего для cache), а раздел 83 запрещает делать P0
зависимым от внешнего обязательного сервиса. Поэтому здесь ровно одно
правило, применяемое единообразно ко всем операциям: любая ошибка Redis —
это кэш-промах, а не сбой запроса. Вызывающий код всегда получает `None` на
чтении и просто продолжает обычным путём к БД; на записи — тихо ничего не
кэширует. Само место в коде, что и что кэшировать, вместе с TTL и
инвалидацией, остаётся в модулях, которым эти данные принадлежат
(`app.matching.service`, `app.vacancies.service`, `app.auth.service`) — этот
модуль ничего не знает о конкретных данных.
"""

import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger("app.cache")

# Redis не должен становиться причиной, по которой запрос выполняется дольше,
# чем без кэша вовсе — короткий таймаут, а не значение по умолчанию клиента.
_REDIS_TIMEOUT_SECONDS = 2.0

_client: "redis.Redis[bytes] | None" = None
# Тестовый рубильник, а не продуктовая настройка: большинство тестов держит
# кэш выключенным (`set_enabled(False)`), потому что их фикстуры меняют
# `Vacancy`/`User` напрямую через ORM в обход `app.vacancies.service` и
# `app.auth.service`, а значит и мимо инвалидации — без выключения кэш отдавал
# бы состояние до такой прямой правки. Поведение самого кэша (наполнение,
# инвалидация, устойчивость к недоступности Redis) проверяется отдельно, с
# кэшем явно включённым, в `tests/test_cache.py`.
_enabled = True


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value


def _active() -> bool:
    return _client is not None and _enabled


async def connect() -> None:
    """Поднимает клиент при старте приложения (раздел 72: инфраструктура
    опциональна). Недоступный на старте Redis не должен мешать API подняться —
    как и MAX Bot в `app.main.lifespan`, кэш просто остаётся выключенным."""
    global _client
    if not settings.redis_url:
        _client = None
        return

    client: "redis.Redis[bytes]" = redis.from_url(
        settings.redis_url,
        socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_TIMEOUT_SECONDS,
    )
    try:
        await client.ping()
    except RedisError:
        logger.warning("Redis недоступен при старте — кэш отключён", exc_info=True)
        await client.aclose()
        _client = None
        return
    _client = client
    logger.info("Redis подключён")


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get_json(key: str) -> Any | None:
    """Значение по ключу или `None` — как при промахе, так и при недоступном
    Redis: вызывающий код не различает эти два случая и просто идёт в БД."""
    if not _active():
        return None
    try:
        raw = await _client.get(key)
    except RedisError:
        logger.warning("Redis недоступен на чтении ключа %s", key, exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # Повреждённое значение (например, после смены формата кэша) —
        # тоже промах, а не 500: следующая запись перезапишет его корректным.
        logger.warning("Не удалось разобрать кэш по ключу %s", key)
        return None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    if not _active():
        return
    try:
        await _client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except RedisError:
        logger.warning("Redis недоступен на записи ключа %s", key, exc_info=True)


async def delete(*keys: str) -> None:
    if not _active() or not keys:
        return
    try:
        await _client.delete(*keys)
    except RedisError:
        logger.warning("Redis недоступен на удалении ключей %s", keys, exc_info=True)


async def flush_all() -> None:
    """Полностью очищает текущую БД Redis. Только для тестов — на проде
    работает выбранной по `REDIS_URL` БД (индекс в пути DSN), поэтому вызов
    вне тестового окружения задел бы чужой кэш."""
    if _client is None:
        return
    try:
        await _client.flushdb()
    except RedisError:
        logger.warning("Redis недоступен на очистке тестовой БД", exc_info=True)


async def delete_prefix(prefix: str) -> None:
    """Удаляет все ключи с данным префиксом — например, все страницы списка
    вакансий одного работодателя сразу, без хранения списка постраничных
    ключей отдельно."""
    if not _active():
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await _client.scan(
                cursor=cursor, match=f"{prefix}*", count=200
            )
            if keys:
                await _client.delete(*keys)
            if cursor == 0:
                break
    except RedisError:
        logger.warning(
            "Redis недоступен на удалении по префиксу %s", prefix, exc_info=True
        )
