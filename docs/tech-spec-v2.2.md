# MAX Найм — техническое задание для разработчиков

**Версия:** 2.0  
**Дата исходного ТЗ:** 20.09.2026  
**Назначение документа:** единое техническое ТЗ для backend/frontend-разработки MVP и последующих P1–P3 функций.

---

## 1. Назначение продукта

MAX Найм — сервис внутри MAX, который позволяет микробизнесу пройти путь от потребности в сотруднике до назначенного собеседования с минимальным количеством ручных действий.

Основной пользовательский маршрут:

```text
Авторизация через MAX
        ↓
Выбор роли
        ↓
Работодатель создаёт вакансию
        ↓
Вакансия опубликована
        ↓
Кандидат создаёт профиль
        ↓
Кандидат получает подходящие вакансии
        ↓
Отклик
        ↓
Screening
        ↓
Hard filters
        ↓
Карточка кандидата работодателю
        ↓
Отклонить / В резерв / Пригласить
        ↓
Взаимный интерес
        ↓
Выбор слота
        ↓
Собеседование назначено
```

Для P0 конечный результат — `Interview scheduled`.

---

# 2. Приоритеты

## P0 — обязательно

Полностью рабочий основной маршрут:

1. запуск Mini App;
2. авторизация через MAX `initData`;
3. создание/обновление пользователя;
4. выбор роли;
5. профиль кандидата;
6. создание вакансии;
7. публикация вакансии;
8. лента вакансий;
9. отклик;
10. screening;
11. hard filters;
12. карточка кандидата;
13. решение работодателя;
14. mutual interest;
15. слоты;
16. бронирование;
17. интервью;
18. уведомление пользователя через MAX Bot API.

P0 не должен зависеть от AI.

## P1

- AI-разбор вакансии;
- голосовой ввод;
- реальные свайпы;
- анонимная карточка;
- explainability;
- ranking;
- причина отказа;
- reserve;
- status board.

## P2

- калибровка работодателя;
- повторное использование screening answers;
- автоматические статусы;
- сообщения об отказе;
- CV parsing;
- talent pool;
- обучение на решениях работодателя;
- referral links;
- аналитика работодателя.

## P3

- AI-интервью;
- skill tests;
- team hiring;
- external calendar;
- job board integrations;
- документы/onboarding;
- полноценный ATS.

---

# 3. Технологический стек

## Backend

Обязательный стек:

- Python 3.10+;
- FastAPI;
- Pydantic v2;
- Tortoise ORM;
- `maxapi`;
- Uvicorn;
- PostgreSQL рекомендуется для production.

`maxapi` предоставляет асинхронный интерфейс к MAX Bot API, Dispatcher/Router/middleware, webhook и интеграцию с FastAPI. Для FastAPI устанавливать:

```bash
pip install "maxapi[fastapi]"
```

Для production использовать webhook, а не long polling. Документация `maxapi` прямо рекомендует webhook для production. 

## Frontend

- React;
- TypeScript;
- MAX UI;
- MAX Bridge;
- mobile + web.

## Infrastructure

- Docker;
- Docker Compose;
- HTTPS;
- environment variables;
- PostgreSQL;
- Redis — только если понадобится для очередей/FSM/cache.

## Локальное файловое хранилище

Для файлов, которые должны сохраняться приложением (в частности, аватарок и файлов резюме), использовать локальное файловое хранилище на сервере. PostgreSQL не используется для хранения бинарного содержимого файлов.

Базовая структура:

```text
storage/
├── avatars/
│   └── {user_id}/
│       └── avatar.{ext}
└── resumes/
    └── {user_id}/
        └── {file_id}.{ext}
```

Для Docker каталог `storage` должен быть вынесен в persistent volume, чтобы файлы не терялись при пересоздании контейнера. Пути к файлам хранятся в БД в соответствующих сущностях.

---

# 4. Общая архитектура

```text
                       ┌──────────────────────┐
                       │         MAX          │
                       │                      │
                       │  Mini App + Bot      │
                       └──────────┬───────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
              Mini App / Bridge             Bot API
                    │                           │
                    ▼                           ▼
          ┌──────────────────┐       ┌──────────────────┐
          │     Frontend     │       │     maxapi       │
          │ React + TS       │       │ Bot / Dispatcher │
          │ MAX UI           │       │ Webhook          │
          └────────┬─────────┘       └────────┬─────────┘
                   │                          │
                   └──────────┬───────────────┘
                              ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │                      │
                    │ Auth                 │
                    │ Users                │
                    │ Vacancies            │
                    │ Applications         │
                    │ Matching             │
                    │ Interviews            │
                    │ Notifications        │
                    │ AI Adapter            │
                    │ Analytics             │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │   PostgreSQL    │         │ External AI     │
        └─────────────────┘         └─────────────────┘
```

Backend является источником истины для состояния и бизнес-логики.

Frontend не имеет права самостоятельно менять бизнес-статусы.

---

# 5. MAX Mini App

Frontend запускается внутри MAX Mini App.

Использовать:

```typescript
window.WebApp
```

Для авторизации использовать:

```typescript
window.WebApp.initData
```

`initDataUnsafe` не использовать как источник доверенной информации для авторизации.

`initData` отправляется на backend целиком, без пересборки на frontend.

---

# 6. Авторизация через MAX initData

## 6.1 Frontend

При запуске Mini App:

```text
window.WebApp.initData
        ↓
POST /auth/max
```

Request:

```json
{
  "init_data": "query_id=...&user=...&auth_date=...&hash=..."
}
```

`init_data` должен быть исходной строкой.

Не отправлять только:

```json
{
  "user_id": 123456
}
```

## 6.2 Backend

Backend обязан:

1. получить `init_data`;
2. разобрать параметры;
3. извлечь `hash`;
4. исключить `hash` из проверяемых параметров;
5. URL-decode значения;
6. отсортировать параметры по ключу;
7. собрать строку проверки через `\n`;
8. получить секретный ключ согласно алгоритму MAX;
9. вычислить HMAC-SHA256;
10. сравнить результат с переданным `hash`;
11. проверить `auth_date`;
12. только после успешной проверки доверять `user`.

Секрет bot token хранить только на backend.

```env
MAX_BOT_TOKEN=...
```

Официальная документация MAX описывает серверную проверку стартовых параметров через HMAC-SHA256.

---

# 7. POST /auth/max

```http
POST /auth/max
Content-Type: application/json
```

### Request

```json
{
  "init_data": "..."
}
```

### Успешный ответ

```json
{
  "user": {
    "user_id": 123456789,
    "first_name": "Иван",
    "last_name": "Петров",
    "username": "ivan_petrov",
    "language_code": "ru",
    "role": null
  },
  "current_step": "role_selection"
}
```

`current_step` нужен frontend для восстановления пользователя не на стартовый экран, а на актуальный шаг сценария при повторном открытии Mini App (требование UX-карты, экран `G01`: «после перезагрузки mini-app пользователь возвращается в релевантное серверное состояние, а не всегда на старт»).

Backend вычисляет `current_step` на основе текущего состояния пользователя, не храня его как отдельное персистентное поле:

```text
role = NULL                                   → "role_selection"
role = candidate, профиля нет                 → "candidate_profile"
role = candidate, есть активный application    → "application_status" (application_id)
role = candidate, профиль есть, откликов нет   → "feed"
role = employer, вакансий нет                 → "vacancy_create"
role = employer, есть вакансии                 → "employer_home"
```

Точный набор значений `current_step` и связанных с ними экранов фиксируется совместно с frontend (см. `G01`–`G03`, `E01`, `C01`–`C02` в UX-карте) до начала интеграции.

После успешной проверки backend:

1. получает `user_id` из MAX;
2. если пользователя ещё нет — создаёт запись `users`, заполняя `first_name`, `last_name`, `username`, `language_code`;
3. если пользователь уже существует — сохраняет пользовательские `first_name` и `last_name`, так как они могли быть изменены внутри MAX Найм;
4. при повторной авторизации может обновить актуальный `username` и `language_code`;
5. обновляет `last_auth_at`;
6. создаёт серверную session;
7. устанавливает HTTP-only cookie;
8. вычисляет `current_step` по текущему состоянию пользователя.

Авторизация не должна перезаписывать вручную изменённые пользователем `first_name` и `last_name` данными MAX при каждом входе.

---

# 8. Таблица users

Отдельный внутренний идентификатор пользователя НЕ создавать.

`user_id` является одновременно:

- идентификатором пользователя MAX;
- идентификатором пользователя в БД;
- PRIMARY KEY.

Имя и фамилия хранятся в одной паре полей. При первой авторизации они заполняются данными из MAX. После этого пользователь может изменить их в MAX Найм. Отдельно хранить «имя из MAX» и «имя пользователя» не нужно.

```sql
CREATE TABLE users (
    user_id          BIGINT PRIMARY KEY,
    first_name       VARCHAR(100) NOT NULL,
    last_name        VARCHAR(100),
    username         VARCHAR(100),
    language_code    VARCHAR(10),
    role             VARCHAR(20) NULL,
    avatar_path      VARCHAR(500) NULL,
    avatar_updated_at TIMESTAMP NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    last_auth_at     TIMESTAMP NOT NULL DEFAULT NOW()
);
```

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `user_id` | BIGINT | Нет | PK | Уникальный идентификатор пользователя в MAX. Используется как основной идентификатор пользователя во всей системе. |
| `first_name` | VARCHAR(100) | Нет | — | Имя пользователя. При первой авторизации заполняется из MAX; пользователь может изменить его в MAX Найм. |
| `last_name` | VARCHAR(100) | Да | — | Фамилия пользователя. При первой авторизации заполняется из MAX; пользователь может изменить её в MAX Найм. |
| `username` | VARCHAR(100) | Да | — | Username пользователя в MAX, если он предоставлен. |
| `language_code` | VARCHAR(10) | Да | — | Язык пользователя, полученный из MAX. Используется в будущем для локализации интерфейса и уведомлений. |
| `role` | VARCHAR(20) | Да | `candidate`, `employer` или `NULL` | Роль пользователя внутри MAX Найм. `NULL` означает, что пользователь ещё не выбрал роль. |
| `avatar_path` | VARCHAR(500) | Да | — | Путь к текущей аватарке пользователя в локальном файловом хранилище. `NULL`, если аватарка не установлена. |
| `avatar_updated_at` | TIMESTAMP | Да | — | Дата и время последней установки или замены аватарки. |
| `created_at` | TIMESTAMP | Нет | — | Дата и время создания пользователя в системе. |
| `updated_at` | TIMESTAMP | Нет | — | Дата и время последнего изменения данных пользователя. |
| `last_auth_at` | TIMESTAMP | Нет | — | Дата и время последней успешной авторизации через MAX. |

## Role

Допустимые значения:

```text
NULL
candidate
employer
```

`NULL` — нормальное состояние нового пользователя.

Авторизация НЕ назначает роль.

## Изменение имени и фамилии

Пользователь должен иметь возможность изменить имя и фамилию, даже если первоначально MAX передал другие значения.

Endpoint:

```http
PATCH /users/me/profile
```

Пример:

```json
{
  "first_name": "Алексей",
  "last_name": "Иванов"
}
```

Backend изменяет только профиль текущего пользователя. `user_id` из request body не принимается как источник идентификации пользователя.

# 9. Выбор роли

Endpoint:

```http
PATCH /users/me/role
```

Request:

```json
{
  "role": "employer"
}
```

или:

```json
{
  "role": "candidate"
}
```

Backend:

- проверяет session;
- валидирует enum;
- изменяет роль текущего пользователя;
- создаёт analytics event `role_selected`.

Нельзя передавать `user_id` для изменения роли.

---

# 10. Sessions

Назначение: серверные сессии авторизованных пользователей Mini App. Сессия связывает cookie браузера с конкретным `users.user_id`.

```sql
CREATE TABLE sessions (
    id            UUID PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(user_id),
    expires_at    TIMESTAMP NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
```

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | UUID | Нет | PK | Уникальный идентификатор серверной сессии. Не должен передаваться frontend как идентификатор пользователя. |
| `user_id` | BIGINT | Нет | FK → `users.user_id` | Пользователь, которому принадлежит сессия. |
| `expires_at` | TIMESTAMP | Нет | — | Дата и время истечения сессии. |
| `created_at` | TIMESTAMP | Нет | — | Дата и время создания сессии. |
| `last_used_at` | TIMESTAMP | Нет | — | Дата и время последнего использования сессии. |

Cookie:

```text
HttpOnly
Secure
SameSite
```

Транспорт сессии — cookie ИЛИ заголовок `Authorization: Bearer <session.id>`.

`POST /auth/max` всегда устанавливает cookie (как выше) и дополнительно
возвращает то же значение `session.id` в теле ответа (`AuthMaxResponse.session_token`).
Backend принимает сессию из cookie, а если её нет — из заголовка `Authorization`.

Причина: в native-обёртке MAX Mini App открывается как обычная страница, и
cookie backend считается «своей». В web.max.ru тот же Mini App встроен во
фрейм на странице MAX — cookie backend становится сторонней, и браузер её
блокирует (вход через `/auth/max` проходит, но следующий запрос уже без
сессии). Заголовок `Authorization` не подвержен блокировке сторонних cookie,
поэтому frontend отправляет его на каждый запрос, когда токен получен из
ответа `/auth/max` (см. `frontend/src/api/client.ts`, `setSessionToken`).

Личность пользователя по-прежнему определяется только серверной сессией:
`session.id` — единственный ключ, куда бы он ни пришёл (cookie или заголовок),
и остаётся непрозрачным для frontend значением, а не источником истины,
который frontend может подделать.

Все защищённые endpoint'ы получают текущего пользователя из session.

Frontend не передаёт `user_id`, `candidate_id` или `employer_id` как источник истины.

---

# 11. Middleware авторизации

Создать FastAPI dependency:

```python
current_user
```

и зависимости:

```python
require_auth
require_candidate
require_employer
```

Пример логики:

```text
request
  ↓
session cookie
  ↓
session
  ↓
users.user_id
  ↓
current_user
  ↓
role check
  ↓
endpoint
```

---

# 12. Ограничения при role = NULL

До выбора роли разрешены только onboarding endpoints.

Запрещено:

- создавать вакансию;
- создавать профиль кандидата;
- откликаться;
- создавать match;
- бронировать интервью.

После выбора роли:

```text
candidate → candidate endpoints
employer  → employer endpoints
```

---

# 13. Модель данных

Минимальные таблицы:

```text
users
sessions
candidate_profiles
vacancies
vacancy_criteria
screening_questions
applications
screening_answers
employer_decisions
matches
interview_slots
interviews
referral_links
analytics_events
```

Все внешние ключи на пользователя ссылаются на `users.user_id`. Отдельного внутреннего `users.id` нет.

---

# 14. candidate_profiles

Назначение: профиль кандидата, используемый для подбора вакансий.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `user_id` | BIGINT | Нет | PK, FK → `users.user_id` | Пользователь, которому принадлежит профиль кандидата. |
| `desired_role` | VARCHAR(255) | Нет | — | Желаемая должность или тип работы кандидата. |
| `city` | VARCHAR(255) | Да | — | Город кандидата. |
| `salary` | NUMERIC | Да | — | Желаемый уровень заработной платы кандидата. |
| `schedule` | VARCHAR(100) | Да | — | Предпочтительный график работы. |
| `experience_months` | INTEGER | Да | `>= 0` | Общий релевантный опыт в месяцах. |
| `available_from` | DATE | Да | — | Дата, с которой кандидат готов приступить к работе. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания профиля. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения профиля. |

Связь: `users.user_id` → `candidate_profiles.user_id`, 1:1.

---

# 15. vacancies

Назначение: вакансия работодателя.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор вакансии. |
| `employer_id` | BIGINT | Нет | FK → `users.user_id` | Пользователь-работодатель, создавший вакансию. |
| `title` | VARCHAR(255) | Нет | — | Название должности. |
| `location` | VARCHAR(255) | Да | — | Место работы или город. |
| `salary_min` | NUMERIC | Да | — | Минимальная указанная зарплата. |
| `salary_max` | NUMERIC | Да | — | Максимальная указанная зарплата. |
| `schedule` | VARCHAR(100) | Да | — | График работы. |
| `status` | VARCHAR(20) | Нет | `draft`, `published`, `closed` | Текущее состояние вакансии. |
| `public_token` | VARCHAR(32) | Да | UNIQUE | Случайный токен для публичной ссылки на вакансию. Генерируется при первой публикации. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания вакансии. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения вакансии. |

`employer_id` → `users.user_id`.

Публичная ссылка (требование UX-карты, экран `E05`: «Ссылка на вакансию» / «Данные: `vacancy_id + public_deep_link`») строится как `{APP_URL}/v/{public_token}`, а не напрямую по `id` — так ссылку можно перегенерировать (например, при подозрении на утечку), не создавая новую вакансию. Токен генерируется один раз при переводе вакансии в `published` и не меняется при последующих правках.

Открытие ссылки без аккаунта MAX — отдельный открытый вопрос к продуктовой команде (см. список вопросов): ведёт ли она на самостоятельную веб-страницу вакансии или работает только как диплинк внутрь MAX Mini App.

Статусы:

```text
draft
published
closed
```

---

# 16. vacancy_criteria

Назначение: формализованные критерии вакансии для hard filters и дальнейшего ranking.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор критерия. |
| `vacancy_id` | BIGINT | Нет | FK → `vacancies.id` | Вакансия, к которой относится критерий. |
| `type` | VARCHAR(50) | Нет | — | Тип критерия: `location`, `schedule`, `salary`, `available_from`, `experience`, `certificate`. |
| `required` | BOOLEAN | Нет | — | Является ли критерий обязательным. |
| `value` | JSONB | Нет | — | Значение критерия в структурированном виде. |
| `weight` | NUMERIC | Да | — | Вес критерия для ranking, если он используется. Для обязательного hard filter решение определяется соответствием критерию. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания критерия. |

---

# 17. applications

Назначение: отклик кандидата на конкретную вакансию.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор отклика. |
| `vacancy_id` | BIGINT | Нет | FK → `vacancies.id` | Вакансия, на которую подан отклик. |
| `candidate_id` | BIGINT | Нет | FK → `users.user_id` | Кандидат, подавший отклик. |
| `status` | VARCHAR(50) | Нет | — | Текущий статус отклика согласно state machine. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания отклика. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения статуса или данных отклика. |

Обязательное ограничение:

```text
UNIQUE(vacancy_id, candidate_id)
```

Допустимые литеральные значения `status` (соответствуют шагам state machine, раздел 26; используются в коде и в UX-карте, например `application.status = hard_filter_failed` на экране `C06`):

```text
created
screening
hard_filter_failed
passed
under_review
rejected
invited
mutual_interest
interview_scheduled
interview_completed
```

`reserved` относится к P1 и добавляется в этот список вместе с реализацией функции «Резерв» (см. раздел 20).

---

# 18. screening_questions

Назначение: вопросы первичного отбора по конкретной вакансии.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор вопроса. |
| `vacancy_id` | BIGINT | Нет | FK → `vacancies.id` | Вакансия, для которой задан вопрос. |
| `question` | TEXT | Нет | — | Текст screening-вопроса. |
| `type` | VARCHAR(50) | Нет | — | Тип ответа, например текст, число, boolean или выбор варианта. |
| `required` | BOOLEAN | Нет | — | Обязателен ли ответ на вопрос. |
| `sort_order` | INTEGER | Нет | — | Порядок отображения вопроса кандидату. |
| `validation_rules` | JSONB | Да | — | Дополнительные правила проверки ответа. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания вопроса. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения вопроса. |

Количество вопросов: **3–4 в P0** (зафиксировано в UX-карте, экран `C05` — «Проверить 3-4 объективных условия»). В P1, если после ИИ-разбора вакансии или калибровки понадобятся дополнительные уточняющие вопросы, диапазон может расширяться до 6. Frontend в P0 должен рассчитывать UI (прогресс-бар «1/N» и т.д.) на 3–4 вопроса, а не закладывать до 6 сразу.

---

# 19. screening_answers

Назначение: ответы кандидата на screening-вопросы конкретного отклика.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор ответа. |
| `application_id` | BIGINT | Нет | FK → `applications.id` | Отклик, в рамках которого дан ответ. |
| `question_id` | BIGINT | Нет | FK → `screening_questions.id` | Вопрос, на который дан ответ. |
| `value` | JSONB | Нет | — | Ответ кандидата в структурированном виде. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания ответа. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения ответа. |

Ограничение:

```text
UNIQUE(application_id, question_id)
```

Исторические ответы заявки не должны автоматически переписываться после изменения профиля кандидата.

---

# 20. employer_decisions

Назначение: история решений работодателя по отклику.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор решения. |
| `application_id` | BIGINT | Нет | FK → `applications.id` | Отклик, по которому принято решение. |
| `action` | VARCHAR(30) | Нет | `rejected`, `reserved`, `invited` | Действие работодателя. |
| `reject_reason` | VARCHAR(50) | Да | — | Причина отказа, если `action = rejected`. |
| `created_at` | TIMESTAMP | Нет | — | Дата и время принятия решения. |

**Приоритет значений `action`:** в P0 backend принимает и валидирует только `rejected` и `invited`. Значение `reserved` относится к P1 (по продуктовому ТЗ «Резерв» — отдельная функция P1, не входит в обязательный P0-маршрут). Колонку и enum можно завести сразу такими, как описано выше, чтобы не делать миграцию позже, но до реализации P1 backend должен отклонять `action = "reserved"` как невалидное значение (`422`).

Причины отказа:

```text
experience
salary
schedule
location
available_from
other
```

---

# 21. matches

Назначение: факт взаимного интереса между кандидатом и работодателем.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор match. |
| `application_id` | BIGINT | Нет | UNIQUE, FK → `applications.id` | Отклик, по которому возник взаимный интерес. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания match. |

Создаётся после взаимного интереса.

---

# 22. interview_slots

Назначение: доступные временные интервалы работодателя для собеседований.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор слота. |
| `employer_id` | BIGINT | Нет | FK → `users.user_id` | Работодатель, создавший слот. |
| `vacancy_id` | BIGINT | Нет | FK → `vacancies.id` | Вакансия, для которой доступен слот. |
| `starts_at` | TIMESTAMP | Нет | — | Дата и время начала собеседования. |
| `ends_at` | TIMESTAMP | Нет | — | Дата и время окончания собеседования. |
| `status` | VARCHAR(20) | Нет | `available`, `booked`, `cancelled` | Текущее состояние слота. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания слота. |

---

# 23. interviews

Назначение: назначенное или проведённое собеседование.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор собеседования. |
| `match_id` | BIGINT | Нет | FK → `matches.id` | Match, в рамках которого назначено собеседование. |
| `slot_id` | BIGINT | Нет | FK → `interview_slots.id` | Забронированный временной слот. |
| `status` | VARCHAR(30) | Нет | `scheduled`, `completed`, `cancelled`, `no_show` | Текущее состояние собеседования. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания собеседования. |
| `updated_at` | TIMESTAMP | Нет | — | Дата последнего изменения состояния. |

Для P0 достаточно состояния `scheduled`.

---

# 24. referral_links

Назначение: ссылки для привлечения кандидатов на конкретную вакансию. P2.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор referral-ссылки. |
| `vacancy_id` | BIGINT | Нет | FK → `vacancies.id` | Вакансия, на которую ведёт ссылка. |
| `source_user_id` | BIGINT | Нет | FK → `users.user_id` | Пользователь, создавший referral-ссылку. |
| `code` | VARCHAR(100) | Нет | UNIQUE | Уникальный код referral-ссылки. |
| `created_at` | TIMESTAMP | Нет | — | Дата создания ссылки. |

---

# 25. analytics_events

Назначение: технический журнал событий пользовательского пути и бизнес-аналитики.

| Поле | Тип | NULL | Ограничения | Описание |
|---|---|---:|---|---|
| `id` | BIGSERIAL | Нет | PK | Уникальный идентификатор аналитического события. |
| `user_id` | BIGINT | Да | FK → `users.user_id` | Пользователь, совершивший действие. Может быть `NULL` для технических событий без пользователя. |
| `event_name` | VARCHAR(100) | Нет | — | Название события, например `vacancy_created`, `application_created`, `interview_booked`. |
| `payload` | JSONB | Да | — | Дополнительные данные события. |
| `timestamp` | TIMESTAMP | Нет | — | Дата и время возникновения события. |

Ошибки аналитики не должны ломать основной пользовательский сценарий.

---

# 26. Application State Machine

```text
Created
   ↓
Screening
   ↓
Failed / Passed
   ↓
Under review
   ├── Rejected
   ├── Reserve (P1)
   └── Invited
           ↓
   Mutual interest
           ↓
   Interview scheduled
           ↓
   Interview completed
           ↓
   Final decision
```

Ветка `Reserve` реализуется в P1; в P0 из `Under review` возможны только переходы в `Rejected` или `Invited`.

Изображённые здесь шаги — это шаги сценария, а не буквальные значения поля `status`. Точный список строковых значений `applications.status` см. в разделе 17.

Изменение статусов выполняется только backend.

---

# 27. API

## Authentication

```http
POST /auth/max
PATCH /users/me/role
```

## User

```http
GET /users/me
PATCH /users/me/profile
GET /users/me/avatar
PATCH /users/me/avatar
DELETE /users/me/avatar
```

`GET /users/me` возвращает текущие данные пользователя, включая роль и данные аватарки.

`PATCH /users/me/profile` изменяет `first_name` и `last_name`. Значения, полученные от MAX при первой авторизации, не считаются неизменяемыми.

`PATCH /users/me/avatar` устанавливает аватарку, если её ещё нет, либо заменяет существующую. Отдельный `POST /users/me/avatar` не нужен.

`DELETE /users/me/avatar` удаляет текущую аватарку и очищает соответствующие поля в `users`.

## Аватар пользователя

Аватарка является необязательной. Сам файл не хранится в PostgreSQL. Используется локальное файловое хранилище приложения.

Рекомендуемая структура:

```text
storage/
└── avatars/
    └── {user_id}/
        └── avatar.{ext}
```

В таблице `users` хранятся только:

- `avatar_path` — путь к текущему файлу;
- `avatar_updated_at` — время последнего изменения.

При замене аватарки старый файл должен быть удалён после успешного сохранения нового файла. При удалении аватарки файл удаляется из локального хранилища, а `avatar_path` и `avatar_updated_at` очищаются.

Ограничения файла (размер, MIME-типы, допустимые расширения и обработка изображения) должны быть заданы backend-конфигурацией и проверяться на сервере.

---

## Candidate

```http
GET /candidate/profile
PATCH /candidate/profile
```

## Vacancies

```http
POST /vacancies
GET /vacancies/:id
GET /vacancies/feed
```

## Applications

```http
POST /vacancies/:id/apply
POST /applications/:id/screening
GET /employer/vacancies/:id/candidates
POST /applications/:id/decision
```

## Interviews

```http
GET /vacancies/:id/slots
POST /vacancies/:id/slots
POST /matches/:id/book
```

## AI

```http
POST /ai/parse-vacancy
POST /ai/transcribe-vacancy
```

## Employer

```http
GET /employer/status-board
GET /employer/analytics
```

---

# 28. Создание вакансии

```http
POST /vacancies
```

Frontend не передаёт `employer_id`.

Backend:

```text
session
 ↓
current_user
 ↓
role == employer
 ↓
validate request
 ↓
create vacancy
```

---

# 29. Публикация вакансии

Перед публикацией проверить обязательные данные:

- title;
- location;
- salary;
- schedule.

Если данные невалидны — вакансия не получает `published`.

---

# 30. Feed

```http
GET /vacancies/feed
```

Для кандидата применяются объективные matching criteria:

- location/radius;
- schedule;
- salary expectations;
- ready date;
- minimum experience, если действительно mandatory;
- required certificate/document.

---

# 31. Запрещённые автоматические критерии

Matching и автоматические решения не должны использовать:

- фотографию/внешность;
- пол;
- возраст, если это не требуется законом;
- charisma;
- reliability;
- culture fit;
- нерелевантные персональные характеристики.

---

# 32. Application

```http
POST /vacancies/:id/apply
```

Проверить:

1. пользователь авторизован;
2. role = candidate;
3. vacancy существует;
4. vacancy = published;
5. application ещё не существует.

После создания:

```text
status = Screening
```

---

# 33. Screening

```http
POST /applications/:id/screening
```

Backend:

1. проверяет владельца application;
2. получает вопросы;
3. валидирует ответы;
4. сохраняет ответы;
5. выполняет hard filters;
6. устанавливает Passed/Failed.

---

# 34. Candidate Card

Employer получает стандартизированную карточку:

- desired role;
- location;
- salary;
- schedule;
- experience;
- available_from;
- screening answers;
- hard filter results.

P1 добавляет:

- anonymity;
- explainability;
- ranking.

---

# 35. Employer Decision

```http
POST /applications/:id/decision
```

Request:

```json
{
  "action": "invited"
}
```

или:

```json
{
  "action": "rejected",
  "reject_reason": "experience"
}
```

Для P1, после реализации функции «Резерв»:

```json
{
  "action": "reserved"
}
```

---

# 36. Match

После взаимного интереса:

```text
application
    ↓
match
```

`matches.application_id` UNIQUE.

---

# 37. Interview Slots

Employer создаёт:

```http
POST /vacancies/:id/slots
```

Candidate получает:

```http
GET /vacancies/:id/slots
```

Candidate выбирает:

```http
POST /matches/:id/book
```

Бронирование должно быть атомарным.

При занятом слоте:

```http
409 Conflict
```

Нельзя создать две interviews на один slot.

---

# 38. MAX Bot интеграция

Для отправки уведомлений использовать библиотеку:

```text
maxapi
```

Документация библиотеки:

https://love-apples.github.io/maxapi/

Библиотека предоставляет асинхронный `Bot`, типизированные методы MAX Bot API, Dispatcher, Router, middleware и FastAPI webhook integration.

Для production использовать webhook, а не polling.

---

# 39. Установка maxapi

Backend dependency:

```bash
pip install "maxapi[fastapi]"
```

или через `uv`:

```bash
uv add "maxapi[fastapi]"
```

На момент подготовки документации актуальная версия `maxapi` в PyPI/GitHub — `1.2.2`; версия должна фиксироваться в dependency lock проекта и обновляться осознанно.

---

# 40. FastAPI + maxapi

Использовать `FastAPIMaxWebhook`.

Архитектура:

```text
FastAPI
 ├── /api/...
 │     └── application REST API
 │
 ├── /webhook/max
 │     └── maxapi webhook
 │
 └── /health
```

Пример архитектурной инициализации:

```python
from fastapi import FastAPI

from maxapi import Bot, Dispatcher
from maxapi.webhook.fastapi import FastAPIMaxWebhook

bot = Bot()
dp = Dispatcher()

webhook = FastAPIMaxWebhook(
    dp=dp,
    bot=bot,
    secret=settings.MAX_WEBHOOK_SECRET,
)

app = FastAPI(
    lifespan=webhook.lifespan,
)

webhook.setup(
    app,
    path="/webhook/max",
)
```

`maxapi` предоставляет готовую FastAPI-интеграцию через `FastAPIMaxWebhook`.

---

# 41. MAX webhook

Production:

```text
MAX
 │
 │ HTTPS POST
 ▼
/webhook/max
 │
 ▼
FastAPIMaxWebhook
 │
 ▼
Dispatcher
 │
 ▼
handlers
```

Webhook должен работать только через HTTPS.

Использовать отдельный secret:

```env
MAX_WEBHOOK_SECRET=...
```

`maxapi` поддерживает проверку заголовка:

```text
X-Max-Bot-Api-Secret
```

и возвращает 403 при неверном/отсутствующем secret.

Не путать:

```text
MAX_BOT_TOKEN
```

и:

```text
MAX_WEBHOOK_SECRET
```

Это разные секреты.

---

# 42. Bot и Mini App — единая backend-система

Bot и Mini App должны использовать один backend.

```text
MAX
 │
 ├── Mini App
 │      │
 │      └── REST API
 │
 └── Bot
        │
        └── maxapi webhook
```

Не создавать отдельный backend для бота.

---

# 43. Bot handlers

Минимально предусмотреть:

```text
/start
bot_started
```

Bot должен уметь открыть Mini App по ссылке/кнопке, если это требуется конфигурацией продукта.

Bot также является каналом уведомлений.

---

# 44. Notification Service

Не отправлять сообщения MAX непосредственно из бизнес-кода каждого endpoint.

Создать отдельный сервис:

```text
NotificationService
```

Например:

```python
await notification_service.send_interview_booked(
    user_id=user.user_id,
    interview=interview,
)
```

Внутри:

```text
NotificationService
        ↓
maxapi Bot
        ↓
send_message
```

---

# 45. Отправка сообщений пользователю

`maxapi` предоставляет `send_message`, который поддерживает отправку в чат или непосредственно пользователю через `user_id`.

Для персональных уведомлений использовать:

```python
await bot.send_message(
    user_id=user.user_id,
    text="..."
)
```

Конкретный метод/сигнатуру закрепить за используемой версией `maxapi`.

---

# 46. Notification types

Уведомление — это сообщение пользователю в MAX, возникающее после бизнес-события. Каждое уведомление должно иметь тип, получателя и ссылку на связанную сущность/событие.

| Тип | Получатель | Когда отправляется | Смысл | Приоритет |
|---|---|---|---|---|
| `application_created` | Работодатель | Кандидат создал отклик | На вакансию поступил новый кандидат | P0 |
| `candidate_invited` | Кандидат | Работодатель пригласил кандидата | Кандидат приглашён к следующему шагу | P0 |
| `mutual_interest` | Участники match | Создан взаимный интерес | Обе стороны получили взаимный интерес | P0 |
| `interview_slot_available` | Кандидат | Работодатель предоставил доступные слоты | Кандидат может выбрать время | P0 |
| `interview_booked` | Кандидат и работодатель | Интервью успешно забронировано | Собеседование назначено | P0 |
| `application_rejected` | Кандидат | Работодатель отклонил отклик | Отклик переведён в отказ | P1/P2 |
| `application_reserved` | Кандидат | Работодатель перевёл кандидата в резерв | Кандидат сохранён в резерве | P1 |
| `interview_cancelled` | Кандидат и работодатель | Собеседование отменено | Уведомление об отмене | P1 |
| `interview_rescheduled` | Кандидат и работодатель | Время собеседования изменено | Уведомление о новом времени | P1/P2 |
| `interview_reminder` | Кандидат и работодатель | Наступил момент напоминания | Напоминание о предстоящем собеседовании | P2 |
| `application_status_changed` | Кандидат | Изменился статус отклика | Информирование об изменении состояния | P2 |

Для P0 обязательны как минимум `application_created`, `candidate_invited`, `mutual_interest`, `interview_slot_available`, `interview_booked`. Остальные типы могут быть реализованы по приоритетам P1–P2.

Текст сообщения должен формироваться NotificationService, а не дублироваться по endpoint'ам.

# 47. Notification flow

Например, интервью назначено:

```text
Candidate
   ↓
POST /matches/:id/book
   ↓
DB transaction
   ├── slot = booked
   ├── interview = scheduled
   └── application = interview_scheduled
   ↓
transaction commit
   ↓
NotificationService
   ↓
maxapi
   ↓
MAX message
```

**Важно:** ошибка MAX notification не должна откатывать успешное создание interview.

---

# 48. Notification logging

Добавить техническое логирование:

```text
notification type
user_id
entity_id
provider
status
error
created_at
```

Можно реализовать отдельной таблицей:

```text
notification_logs
```

или через `analytics_events`, если для P0 достаточно аналитического журнала.

Для production рекомендуется отдельная `notification_logs`.

---

# 49. Retry notifications

Если MAX API временно недоступен:

```text
send
 ↓
temporary error
 ↓
retry
 ↓
success / failed
```

Retry не должен повторно создавать interview.

Notification должен быть идемпотентным на уровне события.

---

# 50. Notification idempotency

Для критичных уведомлений сформировать уникальный ключ:

```text
event_type + entity_id + user_id
```

Например:

```text
interview_booked:123:456
```

Повторная обработка этого события не должна отправлять сообщение бесконечное число раз.

---

# 51. Webhook lifecycle

При запуске production-приложения:

```text
FastAPI startup
      ↓
initialize maxapi Bot
      ↓
initialize Dispatcher
      ↓
register webhook
```

При остановке:

```text
FastAPI shutdown
      ↓
cleanup maxapi resources
```

Использовать lifespan `FastAPIMaxWebhook`.

---

# 52. Pydantic

Все HTTP request/response models описывать через Pydantic.

Примеры:

```python
class AuthMaxRequest(BaseModel):
    init_data: str
```

```python
class RoleUpdateRequest(BaseModel):
    role: UserRole
```

```python
class VacancyCreateRequest(BaseModel):
    title: str
    location: str
    salary_min: int | None
    salary_max: int | None
    schedule: str
```

ORM models и API schemas не смешивать.

---

# 53. Tortoise ORM

Tortoise используется как ORM.

Модели должны отражать:

- PK/FK;
- unique;
- indexes;
- nullable;
- default;
- timestamps.

Особое внимание:

```text
users.user_id
```

является PK.

Не создавать второй user ID.

---

# 54. Tortoise relationships

Основные связи:

```text
User
 ├── CandidateProfile 1:1
 ├── Vacancy 1:N
 ├── Application 1:N
 ├── Session 1:N
 └── AnalyticsEvent 1:N

Vacancy
 ├── Criterion 1:N
 ├── ScreeningQuestion 1:N
 ├── Application 1:N
 ├── InterviewSlot 1:N
 └── ReferralLink 1:N

Application
 ├── ScreeningAnswer 1:N
 ├── EmployerDecision 1:N
 └── Match 1:1

Match
 └── Interview 1:1

InterviewSlot
 └── Interview 1:1
```

---

# 55. Database constraints

Обязательно:

```text
users.user_id PK

candidate_profiles.user_id UNIQUE

UNIQUE(vacancy_id, candidate_id)

UNIQUE(application_id, question_id)

matches.application_id UNIQUE

vacancies.public_token UNIQUE

referral_links.code UNIQUE
```

Также индексы:

```text
vacancies.status
vacancies.employer_id
applications.vacancy_id
applications.candidate_id
applications.status
interview_slots.vacancy_id
interview_slots.starts_at
analytics_events.event_name
analytics_events.timestamp
```

---

# 56. Transaction boundaries

Следующие операции выполнять транзакционно.

## Apply

```text
check duplicate
→ create application
```

## Decision

```text
decision
→ status
```

## Match

```text
mutual interest
→ create match
```

## Interview booking

```text
lock slot
→ verify available
→ book slot
→ create interview
→ update application
```

После commit отправляется notification.

---

# 57. Ошибки

## AI unavailable

Переход на ручной ввод.

## Invalid AI JSON

Не публиковать автоматически.

## Duplicate application

Вернуть существующий application.

## Occupied slot

`409 Conflict`.

## Network error

Разрешить retry.

## Closed vacancy

Новые applications запрещены.

## Notification failure

Interview остаётся созданным.

## Unauthorized

`401`.

## Forbidden

`403`.

## Invalid state transition

`409 Conflict`.

## Validation error

`422 Unprocessable Entity`.

---

# 58. AI Adapter

Создать abstraction:

```python
class AIService:
    async def parse_vacancy(...)
    async def transcribe_vacancy(...)
    async def explain_match(...)
```

Конкретный provider не должен быть связан с domain logic.

Timeout и ошибки AI обрабатываются adapter layer.

P0 работает без AI.

---

# 59. Matching

Hard filters:

```text
location
schedule
salary
available_from
mandatory experience
mandatory certificate/document
```

После hard filters:

```text
ranking
```

Ranking не должен автоматически дисквалифицировать пользователя по запрещённым характеристикам.

---

# 60. Analytics events

Минимальные события:

```text
role_selected

vacancy_creation_started
vacancy_created
vacancy_published

vacancy_ai_parse_started
vacancy_ai_parse_completed

vacancy_calibration_completed

vacancy_viewed
vacancy_swiped_left
vacancy_swiped_right

application_created

screening_started
screening_completed

hard_filter_failed
hard_filter_passed

candidate_card_viewed
candidate_rejected
candidate_reserved
candidate_invited

match_created

slot_viewed
interview_booked

notification_sent

status_board_opened

referral_link_created
```

---

# 61. Frontend screens

## Общие

```text
Splash
Loading
Role Selection
Profile
Error
Empty State
```

## Employer

```text
Employer Home
Create Vacancy
Vacancy Preview
Published Vacancy
Candidate List
Candidate Card
Decision
Match
Interview Slots
Interview Scheduled
Status Board
```

## Candidate

```text
Candidate Home
Candidate Profile
Vacancy Feed
Vacancy Card
Screening
Application Status
Match
Interview Slots
Interview Scheduled
```

---

# 62. Status Board

Employer:

```text
Новые
  ↓
Screening
  ↓
На рассмотрении
  ├── Rejected
  ├── Reserve
  └── Invited
       ↓
Mutual interest
       ↓
Interview
       ↓
Completed
```

Endpoint:

```http
GET /employer/status-board
```

---

# 63. P1 — Anonymous Candidate Card

Карточка кандидата должна позволять работать с matching без преждевременного раскрытия персональных данных.

Поля, необходимые для решения о соответствии:

- роль;
- опыт;
- график;
- зарплатные ожидания;
- локация;
- доступность;
- screening answers.

---

# 64. P1 — Explainability

Backend должен возвращать структурированное объяснение matching:

```json
{
  "matched": [
    "schedule",
    "salary",
    "location"
  ],
  "experience": {
    "candidate": 24,
    "required": 12
  }
}
```

Не использовать субъективные характеристики.

---

# 65. P1 — Ranking

Порядок:

```text
vacancies/candidates
       ↓
hard filters
       ↓
ranking
       ↓
display
```

Ranking не заменяет hard filters.

---

# 66. P2 — Employer calibration

Добавляется настройка весов критериев.

Пример:

```text
schedule = 1.0
experience = 0.8
location = 0.7
salary = 1.0
```

Вес используется ranking.

---

# 67. P2 — Talent pool

Кандидаты, прошедшие предыдущие взаимодействия, могут сохраняться для повторного поиска.

Talent pool не должен ломать основную application state machine.

---

# 68. P2 — Referral

Создание:

```http
POST /vacancies/:id/referral
```

Ответ:

```json
{
  "code": "...",
  "url": "..."
}
```

Источник сохраняется в `referral_links`.

---

# 69. P2 — Analytics dashboard

Employer analytics:

- количество просмотров;
- applications;
- screening pass rate;
- invitations;
- mutual interests;
- interviews booked;
- conversion по этапам.

---

# 70. P3

P3 реализуется только после стабильного P0/P1/P2:

- AI interview;
- skill testing;
- team hiring;
- external calendars;
- job board integrations;
- documents;
- onboarding;
- ATS.

---

# 71. Environment variables

Минимально:

```env
APP_ENV=development
APP_URL=https://example.com

DATABASE_URL=postgres://...

MAX_BOT_TOKEN=...
MAX_WEBHOOK_SECRET=...

SESSION_SECRET=...

AI_API_URL=...
AI_API_KEY=...

LOG_LEVEL=INFO
```

Не хранить secrets в Git.

Добавить:

```text
.env.example
```

без реальных секретов.

---

# 72. Docker Compose

Минимально:

```text
backend
frontend
postgres
```

Опционально:

```text
redis
```

Redis нужен только при фактической необходимости:

- background jobs;
- notification queue;
- FSM;
- cache;
- rate limiting.

---

# 73. Project structure

Рекомендуемая структура backend:

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── database.py
│   │
│   ├── auth/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── dependencies.py
│   │
│   ├── users/
│   │   ├── models.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   │
│   ├── vacancies/
│   ├── candidates/
│   ├── applications/
│   ├── interviews/
│   ├── matching/
│   ├── analytics/
│   │
│   ├── notifications/
│   │   ├── service.py
│   │   ├── schemas.py
│   │   └── maxapi.py
│   │
│   ├── bot/
│   │   ├── dispatcher.py
│   │   ├── handlers/
│   │   └── webhook.py
│   │
│   └── ai/
│       ├── interface.py
│       ├── service.py
│       └── schemas.py
│
├── migrations/
├── tests/
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

# 74. Разделение ответственности

## Router

HTTP transport.

Не содержит сложной бизнес-логики.

## Service

Бизнес-логика.

## Repository / ORM

Работа с БД.

## Schema

Pydantic input/output.

## Model

Tortoise ORM.

## NotificationService

MAX notifications.

## Bot handlers

Команды и события MAX Bot.

## AI adapter

Внешний AI.

---

# 75. MAX Bot webhook и REST API

Webhook бота и REST API должны жить в одном FastAPI application.

Например:

```text
https://domain.com/
│
├── /api/auth/max
├── /api/users/me
├── /api/vacancies
├── /api/applications
├── /api/interviews
│
├── /webhook/max
│
└── /health
```

Webhook не должен быть частью обычной REST authorization middleware.

Для webhook используется `FastAPIMaxWebhook` и `MAX_WEBHOOK_SECRET`.

---

# 76. Healthcheck

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Healthcheck не должен требовать user session.

---

# 77. Logging

Логировать:

- request id;
- endpoint;
- status code;
- duration;
- user id, если авторизован;
- business entity id;
- MAX notification errors;
- AI errors.

Не логировать:

- bot token;
- session secret;
- cookie;
- полную `initData`;
- персональные данные без необходимости.

---

# 78. Rate limiting

Минимально предусмотреть защиту для:

```text
/auth/max
/apply
/book
/ai/*
```

Особенно:

```text
POST /auth/max
POST /matches/:id/book
```

---

# 79. Idempotency

Критичные операции должны быть идемпотентными.

Особенно:

```text
apply
book interview
send notification
```

Повтор HTTP-запроса не должен создавать дублирующую бизнес-сущность.

---

# 80. Tests

## Unit

Проверить:

- initData validation;
- role validation;
- matching;
- hard filters;
- state transitions;
- screening validation;
- booking logic.

## Integration

Проверить:

```text
auth → user
user → role
candidate → profile
employer → vacancy
candidate → application
screening
decision
match
slot
interview
notification
```

## E2E

Главный сценарий:

```text
MAX
 ↓
auth
 ↓
role
 ↓
vacancy
 ↓
profile
 ↓
application
 ↓
screening
 ↓
decision
 ↓
match
 ↓
slot
 ↓
interview
```

---

# 81. P0 acceptance criteria

## Auth

- [ ] `initData` принимается backend;
- [ ] подпись проверяется сервером;
- [ ] невалидный `initData` отклоняется;
- [ ] user создаётся автоматически;
- [ ] `user_id` — PK;
- [ ] role = NULL при первом входе;
- [ ] роль выбирается отдельно;
- [ ] session создаётся.

## User profile

- [ ] `GET /users/me` возвращает профиль;
- [ ] `first_name` и `last_name` можно изменить;
- [ ] повторная авторизация не перезаписывает вручную изменённые имя и фамилию;
- [ ] аватарку можно установить через `PATCH /users/me/avatar`;
- [ ] существующую аватарку можно заменить через `PATCH /users/me/avatar`;
- [ ] аватарку можно получить через `GET /users/me/avatar`;
- [ ] аватарку можно удалить через `DELETE /users/me/avatar`;
- [ ] отсутствие аватарки не мешает работе пользователя.

## Candidate

- [ ] профиль создаётся;
- [ ] feed работает;
- [ ] application создаётся;
- [ ] duplicate application невозможен;
- [ ] screening работает;
- [ ] hard filters работают.

## Employer

- [ ] vacancy создаётся;
- [ ] vacancy публикуется;
- [ ] applications отображаются;
- [ ] candidate card отображается;
- [ ] reject/invite работают (`reserve` — P1, не входит в критерии готовности P0).

## Match

- [ ] match создаётся;
- [ ] candidate получает notification.

## Interview

- [ ] employer создаёт slots;
- [ ] candidate видит slots;
- [ ] slot нельзя занять дважды;
- [ ] interview создаётся;
- [ ] application получает `interview_scheduled`;
- [ ] MAX notification отправляется.

## Bot

- [ ] maxapi подключён;
- [ ] webhook работает;
- [ ] webhook secret проверяется;
- [ ] bot_started обрабатывается;
- [ ] notification service работает;
- [ ] notification failure не ломает interview.

## Infrastructure

- [ ] Docker Compose запускается;
- [ ] migrations выполняются;
- [ ] `.env.example` существует;
- [ ] README существует;
- [ ] healthcheck работает.

---

# 82. Demo

Подготовить:

```text
test employer
test candidate
```

Сценарий:

```text
1. Employer запускает Mini App
2. /auth/max
3. role = employer
4. создаёт vacancy
5. публикует

6. Candidate запускает Mini App
7. /auth/max
8. role = candidate
9. создаёт profile
10. получает vacancy
11. apply
12. screening

13. Employer видит candidate
14. invite

15. Candidate получает MAX notification
16. открывает match
17. выбирает slot

18. Employer получает notification
19. Interview = scheduled
```

Финальный результат:

```text
Собеседование назначено
```

---

# 83. Не ломать проект

Запрещено:

- выносить P0 на внешний обязательный сервис;
- делать AI обязательным для базового сценария;
- хранить секреты на frontend;
- делать user identity доверенной на основании данных frontend;
- менять существующие API без обновления клиентов;
- менять state machine без обновления всех связанных сервисов;
- удалять исторические application data;
- удалять screening answers при изменении профиля;
- откатывать interview из-за ошибки notification.

---

# 84. Технические решения, зафиксированные отдельно

## Пользователь

```text
user_id = PRIMARY KEY
```

Отдельного `users.id` нет.

В `users` хранятся: `user_id`, `first_name`, `last_name`, `username`, `language_code`, `role`, `avatar_path`, `avatar_updated_at`, `created_at`, `updated_at`, `last_auth_at`.

`first_name` и `last_name` при первой авторизации заполняются из MAX, но пользователь может изменить их через `PATCH /users/me/profile`. Отдельные поля для хранения имени/фамилии «из MAX» не создаются.

Аватарка хранится локально; в БД сохраняется путь к текущему файлу. Установка и замена выполняются через `PATCH /users/me/avatar`, удаление — через `DELETE /users/me/avatar`.

## Роль

```text
NULL | candidate | employer
```

Новый пользователь:

```text
role = NULL
```

## Authentication

```text
MAX initData
      ↓
server validation
      ↓
users upsert
      ↓
server session
```

## Bot

```text
maxapi
      ↓
FastAPIMaxWebhook
      ↓
FastAPI
```

## Notifications

```text
Business Service
      ↓
NotificationService
      ↓
maxapi.Bot
      ↓
MAX Bot API
```

## Database

PostgreSQL + Tortoise ORM.

## API schemas

Pydantic v2.

## Business logic

FastAPI routers → services → Tortoise ORM.

---

# 85. Источники и документация

## MAX Mini Apps

https://dev.max.ru/docs/webapps/bridge

Используется для работы с `window.WebApp`, `initData` и контекстом Mini App.

## MAX validation

https://dev.max.ru/docs/webapps/validation

Используется для серверной проверки `initData`.

## MAX Bot API

https://dev.max.ru/docs-api

Используется для Bot API и отправки сообщений.

## MAX UI

https://dev.max.ru/ui

Используется для UI-компонентов Mini App.

## maxapi

https://love-apples.github.io/maxapi/

Python-библиотека для MAX Bot API.

## maxapi examples

https://love-apples.github.io/maxapi/examples/

Содержит примеры webhook, FastAPI и обработчиков.

---

# 86. Важное замечание по maxapi

На момент подготовки документации `maxapi` поддерживает:

- асинхронный `Bot`;
- Dispatcher;
- Router;
- filters;
- middleware;
- webhook;
- FastAPI;
- отправку сообщений;
- inline/callback-механики;
- FSM.

Для production использовать webhook. Документация библиотеки указывает, что long polling ограничен и предназначен прежде всего для разработки. 

Версию `maxapi` зафиксировать в `pyproject.toml`/lock-файле и не использовать плавающую установку в production.

---

# 87. Финальная схема системы

```text
                         MAX
              ┌──────────┴───────────┐
              │                      │
          Mini App                  Bot
              │                      │
        MAX Bridge               Bot API
              │                      │
        initData                 webhook
              │                      │
              ▼                      ▼
       ┌────────────────────────────────────┐
       │              FastAPI               │
       │                                    │
       │ /auth/max                          │
       │ /users/*                           │
       │ /vacancies/*                       │
       │ /applications/*                    │
       │ /matches/*                         │
       │ /interviews/*                      │
       │ /ai/*                              │
       │                                    │
       │ FastAPIMaxWebhook                  │
       └────────────────┬───────────────────┘
                        │
          ┌─────────────┼──────────────┐
          │             │              │
          ▼             ▼              ▼
      Tortoise       maxapi         AI Adapter
          │             │
          ▼             ▼
     PostgreSQL      MAX Bot API
```

**Итоговый P0:** пользователь открывает Mini App → `initData` валидируется на backend → создаётся пользователь с `role = NULL` → выбирается роль → выполняется сценарий найма → backend создаёт interview → `maxapi` отправляет уведомление через MAX → конечное состояние `Interview scheduled`.

Исходное ТЗ проекта требует именно такой сквозной рабочий маршрут, серверное хранение состояния, отсутствие обязательной зависимости P0 от внешних сервисов и отдельную обработку ошибок. 

