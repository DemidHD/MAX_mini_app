#!/bin/sh
# Официальный образ nginx выполняет каждый исполняемый *.sh из
# /docker-entrypoint.d/ перед стартом. Здесь — самоподписанный сертификат на
# случай, если настоящий не подключён через volume (см. nginx/README.md):
# раздел 83 тех-доки запрещает делать P0 зависимым от внешнего обязательного
# сервиса, поэтому HTTPS должен подниматься и без заранее выпущенного
# сертификата. Уже подключённые файлы этот скрипт не трогает.
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "nginx: используется подключённый TLS-сертификат ($CERT_FILE)"
    exit 0
fi

echo "nginx: TLS-сертификат не подключён — генерирую самоподписанный (только для локальной разработки, не для production)"
mkdir -p "$CERT_DIR"
openssl req -x509 -nodes -days 365 \
    -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/CN=localhost" >/dev/null 2>&1
