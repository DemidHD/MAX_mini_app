# Контекст сборки — корень репозитория (docker-compose.yml, `context: .`):
# образу нужны и nginx/, и frontend/.

# 1. Сборка frontend (раздел 72 тех-доки: frontend входит в минимальный
#    состав docker-compose). Vite 8 требует Node 20.19+ / 22.12+.
FROM node:22-alpine AS frontend

WORKDIR /frontend

# Сначала только манифесты — слой с зависимостями кэшируется, пока они не
# меняются.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# 2. Nginx: TLS, статика frontend и прокси на backend.
FROM nginx:1.27-alpine

# openssl — только для генерации запасного самоподписанного сертификата
# (docker-entrypoint.d/10-ensure-tls-cert.sh), когда настоящий не подключён.
RUN apk add --no-cache openssl

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/app-locations.conf /etc/nginx/app-locations.conf
COPY nginx/docker-entrypoint.d/10-ensure-tls-cert.sh /docker-entrypoint.d/10-ensure-tls-cert.sh
# Срезаем CR на случай checkout на Windows с CRLF (см. .gitattributes).
RUN sed -i 's/\r$//' /docker-entrypoint.d/10-ensure-tls-cert.sh \
    && chmod +x /docker-entrypoint.d/10-ensure-tls-cert.sh

COPY --from=frontend /frontend/dist /usr/share/nginx/html
