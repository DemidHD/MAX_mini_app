"""Healthcheck и единый формат ошибок (разделы 57, 76)."""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client() -> AsyncClient:
    # lifespan не запускаем: /health не обращается к базе
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_returns_ok_without_session() -> None:
    async with await _client() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_endpoint_returns_error_envelope() -> None:
    async with await _client() as client:
        response = await client.get("/api/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
