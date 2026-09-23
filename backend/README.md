# MAX Найм — backend

FastAPI + Tortoise ORM + PostgreSQL + `maxapi`. Обслуживает и Mini App
(REST API под `/api`), и бота MAX (webhook на `/webhook/max`) — это одно
приложение, как требует раздел 75 тех-доки.

Источник истины по требованиям — [docs/tech-spec-v2.2.md](../docs/tech-spec-v2.2.md).
Контракты эндпоинтов для frontend — [docs/api-contracts.md](../docs/api-contracts.md).

## Что уже работает (P0)

```text
авторизация MAX initData → выбор роли → профиль кандидата
        ↓                                     ↓
создание и публикация вакансии          лента вакансий
        ↓                                     ↓
        └────────────── отклик ───────────────┘
                          ↓
              первичный отбор и hard filters
                          ↓
                 карточка кандидата
                          ↓
              решение работодателя (invite)
                          ↓
                   взаимный интерес
                          ↓
              слоты → бронирование → Interview scheduled
                          ↓
                 уведомления в MAX Bot API
```

## Быстрый старт

Весь стек поднимается из корня репозитория:

```bash
cp .env.example .env   # заполнить секреты
docker compose up --build
```

Контейнер backend сам применяет миграции (`aerich upgrade`) и запускает
uvicorn на `http://localhost:8000`. Проверка живости — `GET /health`,
интерактивная документация — `/docs`.

## Локальный запуск без Docker

Нужны Python 3.12 и запущенный PostgreSQL.

```bash
cd backend
uv sync
uv run aerich upgrade
uv run uvicorn app.main:app --reload
```

## Переменные окружения

Полный список с комментариями — в [.env.example](../.env.example). Важное:

| Переменная | Смысл |
|---|---|
| `DATABASE_URL` | DSN PostgreSQL для приложения (в Docker хост — `postgres`) |
| `TEST_DATABASE_URL` | DSN для тестов с машины разработчика (`localhost`) |
| `MAX_BOT_TOKEN` | Токен бота: проверка подписи `initData` и Bot API |
| `MAX_WEBHOOK_SECRET` | Секрет webhook'а — **другой** секрет, не равен токену |
| `SESSION_SECRET` | Секрет серверных сессий |
| `BOT_ENABLED` | `false` выключает уведомления и webhook, API работает как обычно |
| `APP_URL` | Адрес Mini App: из него собираются ссылки в уведомлениях |
| `STORAGE_ROOT` | Каталог файлового хранилища (в Docker — persistent volume) |

Секреты в Git не попадают: `.env` в `.gitignore`, в `.env.example` значения пустые.

## Миграции

Используется aerich, конфигурация — в `pyproject.toml` (`[tool.aerich]`).

```bash
uv run aerich migrate --name <название>   # создать миграцию по изменениям моделей
uv run aerich upgrade                     # применить
uv run aerich downgrade                   # откатить последнюю
```

С машины разработчика DSN указывает на хост `postgres` из сети Docker,
поэтому команду нужно запускать с явным адресом:

```bash
DATABASE_URL=postgres://max_hiring:<пароль>@localhost:5432/max_hiring uv run aerich migrate
```

Новая таблица без миграции не появится в боевой БД — это проверяет тест
`test_every_model_module_has_migration`.

## Тесты

```bash
cd backend
uv run pytest
```

Тесты работают с отдельной базой `<db>_test`: она создаётся перед сессией и
удаляется после, данные разработки не трогаются. Схема строится из моделей
(`generate_schemas`), а не из миграций.

Покрытие:

```bash
uv run pytest --cov=app --cov-report=term-missing
```

Бот в тестах выключен, транспорт уведомлений подменён на записывающий:
тесты не ходят в MAX Bot API и не отправляют сообщения живым людям. Боевой
путь `NotificationService → MaxBotTransport → maxapi.Bot` и приём обновлений
`MAX → webhook → диспетчер → обработчик` проверяются в `test_max_integration.py`
на моке бота — с настоящими payload'ами MAX.

Проверка на живом приложении (в том числе с включённым ботом) — отдельный
скрипт:

```bash
docker compose exec backend python scripts/dev_check.py
```

## Структура

```text
app/
├── main.py           точка входа, сборка роутеров, lifespan
├── core/             конфигурация, БД, ошибки, логирование, rate limit, хранилище
├── auth/             initData, сессии, зависимости текущего пользователя
├── users/            профиль и аватарка
├── candidates/       профиль кандидата
├── vacancies/        вакансии, критерии, вопросы отбора, валидация условий
├── matching/         лента и обязательные критерии
├── applications/     отклик, первичный отбор, карточка, решение, match
├── interviews/       слоты, бронирование, собеседования
├── notifications/    NotificationService, тексты, транспорт, журнал доставки
├── bot/              maxapi: бот, диспетчер, обработчики, webhook
├── analytics/        журнал событий
└── ai/               адаптер AI (P1, в P0 не используется)
```

Разделение ответственности — раздел 74 тех-доки: router — транспорт,
service — бизнес-логика, schemas — Pydantic, models — Tortoise.

## Бот и уведомления

Бот и Mini App используют один backend. Webhook принимает обновления на
`/webhook/max` и проверяет заголовок `X-Max-Bot-Api-Secret`; при неверном или
отсутствующем секрете возвращается `403`. Обычной авторизации Mini App на
webhook нет — это отдельный канал (разделы 41, 75).

В production webhook регистрируется в MAX при старте приложения, адрес —
`MAX_WEBHOOK_URL` либо `APP_URL` + `MAX_WEBHOOK_PATH`. Работает только по
HTTPS. В development регистрация не выполняется: локальный адрес из интернета
недоступен.

Уведомления P0 (раздел 46): `application_created`, `candidate_invited`,
`mutual_interest`, `interview_slot_available`, `interview_booked`. Отправляет
их только `NotificationService`, тексты собраны в `app/notifications/messages.py`.

Гарантии:

- ошибка отправки не отменяет бизнес-операцию — созданное собеседование
  остаётся созданным (разделы 47, 83);
- повторная обработка события не шлёт второе сообщение: ключ
  `event_type + entity_id + user_id` уникален в `notification_logs` (раздел 50);
- временная ошибка приводит к повторным попыткам в пределах запроса
  (`NOTIFICATION_MAX_ATTEMPTS`), после чего уведомление помечается `failed`;
- при `BOT_ENABLED=false` уведомление остаётся в статусе `pending`: это не
  отказ, а «канал выключен»;
- `interview_slot_available` приходит один раз на вакансию, а не на каждый
  слот: работодатель заводит время пачкой, и пять сообщений подряд были бы
  спамом.

Фоновой очереди повторов в P0 нет: обязательный маршрут не должен зависеть от
внешней инфраструктуры (раздел 83). Если понадобится — Redis по разделу 72.

## Что осталось вне P0

- AI-разбор вакансии, голосовой ввод, ranking, explainability, резерв,
  доска статусов — P1 (разделы 58, 63–65);
- калибровка, CV, talent pool, referral, аналитика работодателя — P2;
- `under_review` заведён в state machine, но в P0 не используется: экран, где
  он различим, относится к P1.
