"""Фото вакансии по теме. Продуктовое расширение — раздел вне тех-доки.

Openverse — открытый каталог Creative Commons изображений с поиском без
API-ключа (docs.openverse.org): страница результатов по умолчанию — 20
элементов, что и определило формулировку "любая из первых 20 фото". Тема
вакансии берётся из `title` — он уже достаточно конкретен ("Бариста",
"Повар холодного цеха"), отдельный вызов LLM ради этого не нужен.

Сохраняется ссылка, а не файл: раздел 3 запрещает хранить бинарники в
PostgreSQL, а тянуть чужой файл на свой диск здесь и вовсе незачем — сам
Openverse отдаёт постоянные URL с указанием лицензии.

Ошибка поиска или проверки не должна мешать основному сценарию (по аналогии
с разделом 57 — недоступность ИИ не роняет вакансию, а оставляет её без
фото): исключения наружу отсюда не выходят.
"""

import logging
import random

import httpx

from app.core.config import settings
from app.vacancies.models import Vacancy

logger = logging.getLogger("app.vacancies.images")


async def find_image(topic: str) -> str | None:
    """Ищет фото по теме, возвращает ссылку на одно из первых N — случайно.

    `None` — ничего не нашли или сервис недоступен; вызывающий код трактует
    это как отсутствие фото, а не как ошибку.
    """
    query = topic.strip()
    if not settings.vacancy_image_search_enabled or not query:
        return None

    try:
        async with httpx.AsyncClient(
            timeout=settings.vacancy_image_search_timeout_seconds
        ) as client:
            response = await client.get(
                settings.openverse_api_url,
                params={
                    "q": query,
                    "page_size": settings.vacancy_image_candidate_count,
                    "mature": "false",
                },
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Поиск фото вакансии не удался", exc_info=True)
        return None

    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None

    candidates = [
        item["url"]
        for item in results
        if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]
    ]
    if not candidates:
        return None
    return random.choice(candidates)


async def is_reachable(url: str) -> bool:
    """Проверяет, что по ссылке ещё что-то отдаётся.

    HEAD быстрее GET и не тянет тело файла; часть хостингов его не
    поддерживает и отвечает 405 — тогда переспрашиваем через GET с тем же
    коротким таймаутом, прежде чем считать ссылку мёртвой.
    """
    timeout = settings.vacancy_image_liveness_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code == 405:
                response = await client.get(url)
            return response.is_success
    except httpx.HTTPError:
        return False


async def ensure_fresh_image(vacancy: Vacancy) -> str | None:
    """Отдаёт рабочую ссылку на фото, при необходимости подбирая новую.

    Вызывается при отдаче одной вакансии (`GET /vacancies/{id}`): если
    сохранённая ссылка ещё жива — возвращается она же без повторного поиска;
    если умерла или её никогда не было — ищется новая и сохраняется в БД, чтобы
    следующее открытие карточки не искало заново то, что уже нашли только что.
    """
    if vacancy.image_url and await is_reachable(vacancy.image_url):
        return vacancy.image_url

    new_url = await find_image(vacancy.title)
    if new_url != vacancy.image_url:
        vacancy.image_url = new_url
        await vacancy.save(update_fields=["image_url", "updated_at"])
    return new_url
