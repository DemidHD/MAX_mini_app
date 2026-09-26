# Nginx — reverse proxy

Точка входа приложения: терминирует TLS, отдаёт собранный frontend и
проксирует `/api`, `/webhook`, `/health` на `backend`. Не из тех-доки в
деталях конфигурации — тех-дока (раздел 41, раздел 72) требует только
HTTPS и относит frontend к обязательному минимуму docker-compose.

## Порты

`HTTP_PORT` (по умолчанию `8080`) — единственный порт, который публикует
базовый `docker-compose.yml`. На Timeweb App Platform хост-порты 80/443 заняты
платформой: она принимает HTTPS на своём домене и проксирует его на
`HTTP_PORT` первого сервиса манифеста (это nginx) по HTTP. Если такой прокси
прислал `X-Forwarded-Proto: http`, nginx редиректит на HTTPS (раздел 41).

`HTTPS_PORT` (по умолчанию `8443`), прямой доступ к `backend` на `8000`,
порты Postgres и Redis — только в `docker-compose.dev.yml` для локальной
разработки.

## TLS-сертификат

Нужен только для HTTPS самого nginx (локально или на сервере без внешнего
TLS-прокси); на App Platform TLS терминирует платформа. В
`docker-compose.dev.yml` каталог `nginx/certs/` подключён volume'ом в
`/etc/nginx/certs` внутри контейнера. Чтобы подключить настоящий сертификат, положи туда два файла
(имена фиксированы в `nginx/nginx.conf`):

```text
nginx/certs/fullchain.pem
nginx/certs/privkey.pem
```

и перезапусти контейнер (`docker compose restart nginx`). Файлы в `nginx/certs/`
не попадают в git (см. `.gitignore`) — это секрет.

Если оба файла не подключены, контейнер при старте сам генерирует
самоподписанный сертификат (`docker-entrypoint.d/10-ensure-tls-cert.sh`) —
это только для локальной разработки: браузер будет предупреждать о
недоверенном сертификате. Для production обязательно подключи настоящий
(например, выпущенный Let's Encrypt).

## Frontend

Frontend собирается внутри образа nginx (multi-stage `nginx/Dockerfile`:
`npm ci && npm run build` на `node:22-alpine`, затем `dist` копируется в
`/usr/share/nginx/html`). Контекст сборки — корень репозитория, что в него
попадает, задаёт корневой `.dockerignore` (в частности, `frontend/.env.local`
и `node_modules` туда не попадают).

Первый запуск и пересборка после изменений frontend:

```bash
docker compose up -d --build nginx
```

Node на хосте для этого не нужен.
