"""Ручная проверка маршрута P0 на поднятом приложении.

Скрипт собирает initData тем же алгоритмом, что и клиент MAX, подписывает её
токеном из окружения и проходит весь обязательный маршрут: авторизация,
роли, профиль, вакансия, лента, отклик, отбор, решение, слоты и
бронирование. Проверочные данные после прогона удаляет.

В отличие от pytest, скрипт работает на настоящем развёрнутом приложении:
здесь видно, доходят ли уведомления до MAX.

Запуск:
    docker compose exec backend python scripts/dev_check.py

Вывести подписанную initData, чтобы вручную подёргать эндпоинты в /docs:
    docker compose exec backend python scripts/dev_check.py --init-data

Токен бота нигде не печатается.
"""

import argparse
import asyncio
import hmac
import json
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import quote

from pathlib import Path

import asyncpg
import httpx

# Скрипт запускается как файл, поэтому корень проекта нужно добавить руками
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

BASE_URL = "http://localhost:8000"
PROBE_USER_ID = 999000001
PROBE_CANDIDATE_ID = 999000002
PROBE_VACANCY_TITLES = ("Проверочная подходящая", "Проверочная неподходящая")

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64 + b"\xff\xd9"

passed = 0
failed = 0


def check(title: str, condition: bool, details: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [ OK ] {title}{f' — {details}' if details else ''}")
    else:
        failed += 1
        print(f"  [ FAIL ] {title}{f' — {details}' if details else ''}")


def build_init_data(
    first_name: str = "Проверочный", user_id: int = PROBE_USER_ID
) -> str:
    """Собирает и подписывает initData по алгоритму MAX."""
    if not settings.max_bot_token:
        sys.exit("MAX_BOT_TOKEN не задан в .env — подписать initData нечем")

    params = {
        "auth_date": str(int(datetime.now(timezone.utc).timestamp())),
        "chat": json.dumps({"id": 12345, "type": "DIALOG"}, separators=(",", ":")),
        "ip": "192.168.0.1",
        "query_id": "4c0ab423-342b-4e45-aea4-2747dbc500cd",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": first_name,
                "last_name": "Пользователь",
                "username": "probe",
                "language_code": "ru",
                "photo_url": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.max_bot_token.encode(), sha256).digest()
    signature = hmac.new(secret_key, launch_params.encode(), sha256).hexdigest()
    encoded = "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())
    return f"{encoded}&hash={signature}"


async def create_vacancies(client: httpx.AsyncClient, jar: dict) -> dict[str, int]:
    """Создаёт вакансии через API работодателя (разделы 28, 29).

    Одна подходит кандидату по городу, другая нет: первая должна попасть в
    ленту, вторая — быть отсеяна обязательным критерием.
    """
    created: dict[str, int] = {}
    for title, city in zip(PROBE_VACANCY_TITLES, ("Москва", "Казань")):
        response = await client.post(
            "/api/vacancies",
            json={
                "title": title,
                "location": city,
                "salary_min": "60000",
                "salary_max": "90000",
                "schedule": "full_time",
                "status": "published",
                "criteria": [
                    {"type": "location", "required": True, "value": {"city": city}}
                ],
                "questions": [
                    {
                        "question": "Есть ли действующая медкнижка?",
                        "type": "boolean",
                        "required": True,
                        "validation_rules": {"must_equal": True},
                    }
                ],
            },
            cookies=jar,
        )
        check(
            f"вакансия «{title}» создана и опубликована",
            response.status_code == 201,
            response.text if response.status_code != 201 else "",
        )
        if response.status_code == 201:
            body = response.json()
            created[title] = body["id"]
            check(
                "публичная ссылка выдана при публикации",
                bool(body["public_url"]),
                str(body.get("public_url")),
            )
    return created


async def notification_rows() -> list[dict]:
    """Журнал уведомлений по проверочным пользователям (раздел 48)."""
    connection = await asyncpg.connect(settings.database_url)
    try:
        rows = await connection.fetch(
            """
            SELECT event_type, status, attempts
            FROM notification_logs
            WHERE user_id = ANY($1::bigint[])
            ORDER BY id
            """,
            [PROBE_USER_ID, PROBE_CANDIDATE_ID],
        )
    finally:
        await connection.close()
    return [dict(row) for row in rows]


async def cleanup() -> None:
    """Убирает проверочные данные из базы разработки."""
    users = [PROBE_USER_ID, PROBE_CANDIDATE_ID]
    connection = await asyncpg.connect(settings.database_url)
    try:
        # Собеседования удаляются первыми: interviews.slot_id защищён RESTRICT,
        # и каскад от вакансии к слоту без этого не пройдёт
        await connection.execute(
            """
            DELETE FROM interviews
            WHERE slot_id IN (
                SELECT id FROM interview_slots WHERE employer_id = ANY($1::bigint[])
            )
            """,
            users,
        )
        await connection.execute(
            "DELETE FROM vacancies WHERE employer_id = ANY($1::bigint[])", users
        )
        for table in (
            "notification_logs",
            "sessions",
            "analytics_events",
            "candidate_profiles",
            "users",
        ):
            await connection.execute(
                f"DELETE FROM {table} WHERE user_id = ANY($1::bigint[])", users
            )
    finally:
        await connection.close()


async def run() -> None:
    init_data = build_init_data()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        print("\nЗдоровье сервиса")
        health = await client.get("/health")
        check("GET /health отвечает 200 без сессии", health.status_code == 200, health.text)

        print("\nАвторизация (раздел 6-7)")
        login = await client.post("/api/auth/max", json={"init_data": init_data})
        check("вход с подписанной initData", login.status_code == 200, f"код {login.status_code}")
        if login.status_code != 200:
            print(login.text)
            return

        body = login.json()
        cookie = login.cookies.get(settings.session_cookie_name)
        jar = {settings.session_cookie_name: cookie}
        check("роль нового пользователя пустая", body["user"]["role"] is None)
        check("current_step = role_selection", body["current_step"] == "role_selection")
        check("сессионная cookie выдана", bool(cookie))
        check(
            "cookie помечена HttpOnly",
            "httponly" in login.headers.get("set-cookie", "").lower(),
        )

        broken = init_data[:-1] + ("0" if init_data[-1] != "0" else "1")
        bad = await client.post("/api/auth/max", json={"init_data": broken})
        check("подделанная подпись отклонена 401", bad.status_code == 401, bad.json()["error"]["code"])

        # Отдельный клиент: у основного cookie уже сохранена после входа
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as anonymous:
            no_session = await anonymous.get("/api/users/me")
        check("запрос без сессии отклонён 401", no_session.status_code == 401)

        print("\nПользователь и роль (разделы 8-9)")
        me = await client.get("/api/users/me", cookies=jar)
        check("GET /users/me отдаёт профиль", me.status_code == 200 and me.json()["user_id"] == PROBE_USER_ID)

        role = await client.patch("/api/users/me/role", json={"role": "employer"}, cookies=jar)
        check("роль employer выбрана", role.status_code == 200 and role.json()["role"] == "employer")

        wrong_role = await client.patch("/api/users/me/role", json={"role": "admin"}, cookies=jar)
        check("недопустимая роль отклонена 422", wrong_role.status_code == 422)

        profile = await client.patch(
            "/api/users/me/profile", json={"first_name": "Алексей"}, cookies=jar
        )
        check("имя изменено", profile.status_code == 200 and profile.json()["first_name"] == "Алексей")

        empty_name = await client.patch(
            "/api/users/me/profile", json={"first_name": "   "}, cookies=jar
        )
        check("пустое имя отклонено 422", empty_name.status_code == 422)

        relogin = await client.post("/api/auth/max", json={"init_data": build_init_data()})
        relogin_body = relogin.json()
        check(
            "повторный вход не затирает изменённое имя",
            relogin_body["user"]["first_name"] == "Алексей",
            f"MAX прислал «Проверочный», в базе «{relogin_body['user']['first_name']}»",
        )
        check(
            "current_step учитывает состояние",
            relogin_body["current_step"] == "vacancy_create",
            relogin_body["current_step"],
        )

        print("\nАватарка (раздел 27)")
        missing = await client.get("/api/users/me/avatar", cookies=jar)
        check("без аватарки отдаётся 404", missing.status_code == 404)

        upload = await client.patch(
            "/api/users/me/avatar",
            files={"file": ("avatar.png", PNG_BYTES, "image/png")},
            cookies=jar,
        )
        check("аватарка установлена", upload.status_code == 200 and upload.json()["has_avatar"])

        download = await client.get("/api/users/me/avatar", cookies=jar)
        check("аватарка отдаётся обратно", download.content == PNG_BYTES)

        replaced = await client.patch(
            "/api/users/me/avatar",
            files={"file": ("avatar.jpg", JPEG_BYTES, "image/jpeg")},
            cookies=jar,
        )
        check("аватарка заменена", replaced.status_code == 200)

        fake = await client.patch(
            "/api/users/me/avatar",
            files={"file": ("avatar.png", b"#!/bin/sh\nrm -rf /", "image/png")},
            cookies=jar,
        )
        check(
            "скрипт под видом картинки отклонён 422",
            fake.status_code == 422,
            fake.json()["error"]["code"],
        )

        oversized = PNG_BYTES + b"\x00" * settings.avatar_max_size_bytes
        too_big = await client.patch(
            "/api/users/me/avatar",
            files={"file": ("avatar.png", oversized, "image/png")},
            cookies=jar,
        )
        check("слишком большой файл отклонён 422", too_big.status_code == 422)

        removed = await client.delete("/api/users/me/avatar", cookies=jar)
        check("аватарка удалена", removed.status_code == 204)

        gone = await client.get("/api/users/me/avatar", cookies=jar)
        check("после удаления снова 404", gone.status_code == 404)

        print("\nДоступ к ленте (раздел 30)")
        forbidden = await client.get("/api/vacancies/feed", cookies=jar)
        check(
            "работодателю лента недоступна 403",
            forbidden.status_code == 403,
            forbidden.json()["error"]["code"],
        )

        candidate_login = await client.post(
            "/api/auth/max",
            json={"init_data": build_init_data(user_id=PROBE_CANDIDATE_ID)},
        )
        candidate_jar = {
            settings.session_cookie_name: candidate_login.cookies.get(
                settings.session_cookie_name
            )
        }
        await client.patch(
            "/api/users/me/role", json={"role": "candidate"}, cookies=candidate_jar
        )

        empty = await client.get("/api/vacancies/feed", cookies=candidate_jar)
        check(
            "без профиля лента пустая",
            empty.status_code == 200 and empty.json()["items"] == [],
        )

        print("\nПрофиль кандидата (разделы 14, 27)")
        missing = await client.get("/api/candidate/profile", cookies=candidate_jar)
        check(
            "до создания профиля 404",
            missing.status_code == 404,
            missing.json()["error"]["code"],
        )

        no_role = await client.patch(
            "/api/candidate/profile", json={"city": "Москва"}, cookies=candidate_jar
        )
        check(
            "создание без желаемой должности отклонено 422",
            no_role.status_code == 422,
            no_role.json()["error"]["code"],
        )

        created = await client.patch(
            "/api/candidate/profile",
            json={
                "desired_role": "Бариста",
                "city": "Москва",
                "salary": "70000",
                "schedule": "full_time",
                "experience_months": 24,
                "available_from": "2026-10-01",
            },
            cookies=candidate_jar,
        )
        check(
            "профиль создан через PATCH",
            created.status_code == 200 and created.json()["desired_role"] == "Бариста",
            created.text if created.status_code != 200 else "",
        )
        check(
            "зарплата отдаётся в формате колонки",
            created.status_code == 200 and created.json()["salary"] == "70000.00",
            created.json().get("salary") if created.status_code == 200 else "",
        )

        stored = await client.get("/api/candidate/profile", cookies=candidate_jar)
        check(
            "GET возвращает сохранённый профиль",
            stored.status_code == 200 and stored.json() == created.json(),
        )

        partial = await client.patch(
            "/api/candidate/profile", json={"salary": "85000"}, cookies=candidate_jar
        )
        check(
            "частичное изменение не трогает остальные поля",
            partial.status_code == 200
            and partial.json()["salary"] == "85000.00"
            and partial.json()["city"] == "Москва",
        )

        cleared = await client.patch(
            "/api/candidate/profile", json={"city": None}, cookies=candidate_jar
        )
        check(
            "null очищает необязательное поле",
            cleared.status_code == 200 and cleared.json()["city"] is None,
        )

        bad_salary = await client.patch(
            "/api/candidate/profile", json={"salary": "-1"}, cookies=candidate_jar
        )
        check("отрицательная зарплата отклонена 422", bad_salary.status_code == 422)

        foreign = await client.patch(
            "/api/candidate/profile",
            json={"desired_role": "Бариста", "user_id": PROBE_USER_ID},
            cookies=candidate_jar,
        )
        check(
            "user_id из тела запроса игнорируется",
            foreign.status_code == 200
            and foreign.json()["user_id"] == PROBE_CANDIDATE_ID,
        )

        employer_attempt = await client.get("/api/candidate/profile", cookies=jar)
        check(
            "работодателю профиль кандидата недоступен 403",
            employer_attempt.status_code == 403,
            employer_attempt.json()["error"]["code"],
        )

        # Профиль вернули в исходное состояние: лента ниже проверяется по городу
        await client.patch(
            "/api/candidate/profile",
            json={"city": "Москва", "salary": "70000"},
            cookies=candidate_jar,
        )

        print("\nЛента вакансий с профилем (раздел 30)")
        incomplete = await client.post(
            "/api/vacancies",
            json={"title": "Без обязательных данных", "status": "published"},
            cookies=jar,
        )
        check(
            "публикация без обязательных данных отклонена 422",
            incomplete.status_code == 422,
            incomplete.json()["error"]["code"] if incomplete.status_code == 422 else "",
        )

        typo = await client.post(
            "/api/vacancies",
            json={
                "title": "С опечаткой в условии",
                "criteria": [
                    {"type": "location", "required": True, "value": {"cityy": "Москва"}}
                ],
            },
            cookies=jar,
        )
        check(
            "нечитаемое условие вакансии отклонено 422",
            typo.status_code == 422,
            typo.json()["error"]["code"] if typo.status_code == 422 else "",
        )

        vacancies = await create_vacancies(client, jar)
        vacancy_id = vacancies.get(PROBE_VACANCY_TITLES[0])

        feed = await client.get("/api/vacancies/feed", cookies=candidate_jar)
        titles = [item["title"] for item in feed.json()["items"]]
        check(
            "подходящая вакансия в ленте",
            PROBE_VACANCY_TITLES[0] in titles,
            f"получено: {titles}",
        )
        check(
            "вакансия с чужим городом отсеяна",
            PROBE_VACANCY_TITLES[1] not in titles,
        )
        card = next(
            (item for item in feed.json()["items"] if item["title"] == PROBE_VACANCY_TITLES[0]),
            None,
        )
        check(
            "в карточке видны условия вакансии",
            bool(card and card["criteria"]),
            str(card["criteria"]) if card else "карточка не найдена",
        )

        check(
            "total считает все подходящие вакансии",
            feed.json()["total"] == len(feed.json()["items"]),
            f"total={feed.json()['total']}, на странице {len(feed.json()['items'])}",
        )

        bad_paging = await client.get(
            "/api/vacancies/feed", params={"limit": 500}, cookies=candidate_jar
        )
        check("некорректная пагинация отклонена 422", bad_paging.status_code == 422)

        if vacancy_id is None:
            print("\nВакансия не создана — дальше проверять нечего")
            return

        await check_hiring_route(client, jar, candidate_jar, vacancy_id)


async def check_hiring_route(
    client: httpx.AsyncClient,
    jar: dict,
    candidate_jar: dict,
    vacancy_id: int,
) -> None:
    """Отклик, отбор, решение, слоты и бронирование (разделы 32-37, 46)."""
    print("\nОтклик и первичный отбор (разделы 32, 33)")
    applied = await client.post(
        f"/api/vacancies/{vacancy_id}/apply", cookies=candidate_jar
    )
    check(
        "отклик создан",
        applied.status_code == 201,
        applied.text if applied.status_code != 201 else "",
    )
    if applied.status_code != 201:
        return
    application_id = applied.json()["id"]

    repeated = await client.post(
        f"/api/vacancies/{vacancy_id}/apply", cookies=candidate_jar
    )
    check(
        "повторный отклик не дублируется",
        repeated.status_code == 200 and repeated.json()["id"] == application_id,
        f"код {repeated.status_code}",
    )

    screening = await client.get(
        f"/api/applications/{application_id}/screening", cookies=candidate_jar
    )
    check("вопросы отбора получены", screening.status_code == 200)
    question = screening.json()["questions"][0]
    check(
        "отсекающее условие кандидату не показано",
        "must_equal" not in question["rules"],
        str(question["rules"]),
    )

    passed = await client.post(
        f"/api/applications/{application_id}/screening",
        json={"answers": [{"question_id": question["id"], "value": True}]},
        cookies=candidate_jar,
    )
    check(
        "первичный отбор пройден",
        passed.status_code == 200 and passed.json()["status"] == "passed",
        passed.text if passed.status_code != 200 else passed.json()["status"],
    )

    print("\nКарточка кандидата и решение (разделы 34-36)")
    candidates = await client.get(
        f"/api/employer/vacancies/{vacancy_id}/candidates", cookies=jar
    )
    check(
        "кандидат виден работодателю",
        candidates.status_code == 200 and candidates.json()["total"] == 1,
        candidates.text if candidates.status_code != 200 else "",
    )
    card = candidates.json()["items"][0]
    check(
        "в карточке нет персональных данных",
        "Алексей" not in str(card) and "avatar" not in str(card),
    )

    decision = await client.post(
        f"/api/applications/{application_id}/decision",
        json={"action": "invited"},
        cookies=jar,
    )
    check(
        "приглашение переводит отклик во взаимный интерес",
        decision.status_code == 200
        and decision.json()["status"] == "mutual_interest",
        decision.text if decision.status_code != 200 else "",
    )
    match_id = decision.json().get("match_id")
    check("match создан", bool(match_id))

    repeated_decision = await client.post(
        f"/api/applications/{application_id}/decision",
        json={"action": "rejected"},
        cookies=jar,
    )
    check(
        "повторное решение отклонено 409",
        repeated_decision.status_code == 409,
        repeated_decision.json()["error"]["code"]
        if repeated_decision.status_code == 409
        else "",
    )

    print("\nСлоты и бронирование (разделы 37, 56, 57)")
    starts_at = datetime.now(timezone.utc) + timedelta(days=1)
    slot = await client.post(
        f"/api/vacancies/{vacancy_id}/slots",
        json={
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        },
        cookies=jar,
    )
    check(
        "слот создан",
        slot.status_code == 201,
        slot.text if slot.status_code != 201 else "",
    )
    if slot.status_code != 201:
        return
    slot_id = slot.json()["id"]

    naive = await client.post(
        f"/api/vacancies/{vacancy_id}/slots",
        json={
            "starts_at": starts_at.replace(tzinfo=None).isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
        },
        cookies=jar,
    )
    check("время без часового пояса отклонено 422", naive.status_code == 422)

    overlapping = await client.post(
        f"/api/vacancies/{vacancy_id}/slots",
        json={
            "starts_at": (starts_at + timedelta(minutes=30)).isoformat(),
            "ends_at": (starts_at + timedelta(minutes=90)).isoformat(),
        },
        cookies=jar,
    )
    check(
        "пересекающийся слот отклонён 409",
        overlapping.status_code == 409,
        overlapping.json()["error"]["code"] if overlapping.status_code == 409 else "",
    )

    slots = await client.get(
        f"/api/vacancies/{vacancy_id}/slots", cookies=candidate_jar
    )
    check(
        "кандидат видит свободный слот",
        slots.status_code == 200
        and [item["id"] for item in slots.json()["items"]] == [slot_id],
        slots.text if slots.status_code != 200 else "",
    )
    check("кандидату отдан match для бронирования", slots.json()["match_id"] == match_id)

    booked = await client.post(
        f"/api/matches/{match_id}/book",
        json={"slot_id": slot_id},
        cookies=candidate_jar,
    )
    check(
        "собеседование назначено",
        booked.status_code == 201
        and booked.json()["application_status"] == "interview_scheduled",
        booked.text if booked.status_code != 201 else "",
    )

    again = await client.post(
        f"/api/matches/{match_id}/book",
        json={"slot_id": slot_id},
        cookies=candidate_jar,
    )
    check(
        "повторное бронирование не дублирует собеседование",
        again.status_code == 200 and again.json()["id"] == booked.json()["id"],
        f"код {again.status_code}",
    )

    after = await client.get(f"/api/vacancies/{vacancy_id}/slots", cookies=jar)
    check(
        "работодатель видит назначенное собеседование",
        after.status_code == 200
        and after.json()["interviews"]
        and after.json()["interviews"][0]["application_id"] == application_id,
        after.text if after.status_code != 200 else "",
    )

    print("\nУведомления (разделы 46, 48)")
    rows = await notification_rows()
    sent_types = {row["event_type"] for row in rows}
    expected = {
        "application_created",
        "candidate_invited",
        "mutual_interest",
        "interview_slot_available",
        "interview_booked",
    }
    check(
        "по каждому событию P0 заведено уведомление",
        expected <= sent_types,
        f"не хватает: {sorted(expected - sent_types)}" if expected - sent_types else "",
    )
    delivered = [row for row in rows if row["status"] == "sent"]
    check(
        "уведомления доставлены в MAX",
        len(delivered) == len(rows),
        "статусы: "
        + ", ".join(f"{row['event_type']}={row['status']}" for row in rows)
        + " (при BOT_ENABLED=false это ожидаемо)",
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка backend MAX Найм")
    parser.add_argument(
        "--init-data",
        action="store_true",
        help="вывести подписанную initData для ручных запросов в /docs",
    )
    args = parser.parse_args()

    if args.init_data:
        print(build_init_data())
        return 0

    try:
        await run()
    finally:
        await cleanup()

    print(f"\nИтог: успешно {passed}, провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
