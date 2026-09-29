# MAX Найм — Frontend

Mini App на React + TypeScript + [MAX UI](https://dev.max.ru/ui). Технический контракт с backend — в [docs/tech-spec-v2.2.md](../docs/tech-spec-v2.2.md).

## Запуск

```bash
npm install
npm run dev
```

Dev-сервер поднимается на `http://localhost:5173` и проксирует `/api` и `/health` на backend (`http://localhost:8000` по умолчанию, см. `vite.config.ts` и `VITE_API_PROXY_TARGET`). Backend должен быть уже запущен — см. корневой `docker-compose.yml`.

### Авторизация вне клиента MAX

В браузере разработки `window.WebApp` не существует — Mini App может работать только внутри MAX. Чтобы пройти `/auth/max` локально:

1. Получить тестового бота: `MAX_BOT_TOKEN` должен быть задан в `backend/.env`.
2. Сгенерировать подписанную `initData`:
   ```bash
   docker compose exec backend python scripts/dev_check.py --init-data
   ```
3. Положить результат в `frontend/.env.local`:
   ```env
   VITE_DEV_INIT_DATA=auth_date=...&hash=...
   ```

`.env.local` в Git не попадает. `VITE_DEV_INIT_DATA` действует ограниченное время (`AUTH_DATE_MAX_AGE_SECONDS` в backend, по умолчанию 24 часа) — по истечении нужно сгенерировать новую строку.

## Структура

```text
src/
├── api/         REST-клиент (/api/*), типы ответов backend
├── app/         маршруты и роутинг
├── auth/        AuthContext — состояние сессии, current_step
├── bridge/      интеграция с window.WebApp (MAX Mini App)
├── components/  общие UI-компоненты (layout, loading/error/empty)
└── pages/       экраны
```

## Проверки

```bash
npm run lint   # oxlint
npx tsc -b     # проверка типов
npm run build  # production-сборка
```
