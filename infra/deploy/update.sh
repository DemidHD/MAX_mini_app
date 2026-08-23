#!/usr/bin/env bash
#
# Выкладка на стенде. Сервер сам ходит в реестр и обновляется — снаружи в него
# никто не стучится.
#
# Так сделано не из любви к таймерам, а потому что входящий SSH с раннеров
# GitHub до этого сервера не доходит: TCP устанавливается, баннер проходит,
# а обмен ключами встаёт намертво — одинаково на 22 и 2222, одинаково с полным
# и с урезанным набором алгоритмов (решение Р71). Направление «сервер наружу»
# при этом рабочее, поэтому вся связь развёрнута в эту сторону.
#
# Запускается таймером systemd. Ничего не делает, если выкладывать нечего.

set -euo pipefail

REPO=Danil-prog-coder/MAX_mini_app
# Каталог стенда. Переопределяется переменной окружения — это нужно тестам,
# которые прогоняют скрипт целиком на подставных docker и curl.
ROOT=${NAVIGATOR_ROOT:-/opt/navigator}
PREFIX=ghcr.io/danil-prog-coder/max_mini_app
COMPOSE_FILE=docker-compose.prod.yml

# Долгоживущие сервисы. migrate и seed сюда не входят намеренно: они разовые и
# в нормальном состоянии именно что не запущены.
SERVICES='caddy core-api miniapp ai-gateway'

cd "$ROOT"

if [ ! -f .env ]; then
  echo "нет $ROOT/.env — создайте его по .env.example из репозитория" >&2
  exit 1
fi

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# ── 1. Что опубликовано ──────────────────────────────────────────────────────
# Тег latest — указатель на последнюю сборку main. Разбираться, что именно за
# ним стоит, нужно по метке образа, а не по имени тега: тег переезжает, а метка
# называет коммит.
if ! docker pull -q "$PREFIX/core:latest" > /dev/null; then
  echo "не удалось забрать $PREFIX/core:latest." >&2
  echo "Если ответ был 401 — пакеты в GHCR ещё приватные, сделайте их публичными." >&2
  exit 1
fi

revision=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$PREFIX/core:latest")
if [ -z "$revision" ]; then
  echo "у образа нет метки org.opencontainers.image.revision — нечем определить коммит" >&2
  exit 1
fi

# Дальше все обращения к compose идут с этим тегом: на сервере всегда видно,
# что именно выложено, а откат — это запуск с прежним значением (решение Р70).
export IMAGE_TAG="$revision"

# ── 2. Нужно ли что-то делать ────────────────────────────────────────────────
deployed=$(cat "$ROOT/.deployed" 2>/dev/null || true)

all_running() {
  local svc
  for svc in $SERVICES; do
    [ -n "$(compose ps -q --status running "$svc" 2>/dev/null)" ] || return 1
  done
}

if [ "$revision" = "$deployed" ] && all_running; then
  exit 0
fi

echo "выкладываю $revision (было: ${deployed:-ничего})"

# ── 3. Конфигурация — того же коммита, что и образы ──────────────────────────
# Скачивается во временный каталог целиком и только потом ставится на место:
# наполовину обновлённая конфигурация хуже необновлённой.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

raw="https://raw.githubusercontent.com/$REPO/$revision"
mkdir -p "$tmp/infra/caddy/conf.d"
curl -fsSL "$raw/$COMPOSE_FILE"                          -o "$tmp/$COMPOSE_FILE"
curl -fsSL "$raw/infra/caddy/Caddyfile"                  -o "$tmp/infra/caddy/Caddyfile"
curl -fsSL "$raw/infra/caddy/conf.d/admin.caddy.example" -o "$tmp/infra/caddy/conf.d/admin.caddy.example"

mkdir -p "$ROOT/infra/caddy/conf.d"
install -m 644 "$tmp/$COMPOSE_FILE"                          "$ROOT/$COMPOSE_FILE"
install -m 644 "$tmp/infra/caddy/Caddyfile"                  "$ROOT/infra/caddy/Caddyfile"
install -m 644 "$tmp/infra/caddy/conf.d/admin.caddy.example" "$ROOT/infra/caddy/conf.d/admin.caddy.example"

# ── 4. Подъём ────────────────────────────────────────────────────────────────
compose pull -q
# migrate и seed — разовые сервисы, compose отработает их до старта приложения:
# подниматься на несовпадающей схеме нельзя.
compose up -d --remove-orphans

# Caddy читает конфиг при старте, а `compose up` не пересоздаёт контейнер из-за
# того, что изменилось содержимое bind-монтированного файла: для compose сервис
# не менялся — ни образ, ни определение. Без этого новый Caddyfile лёг бы на
# диск и остался непрочитанным.
#
# Перечитываем безусловно, а не по изменению файла. Сравнение слепков «до
# и после» выглядело экономнее, но у него есть дыра, в которую мы уже попали:
# если файл на диске обновился раньше, чем появилась перезагрузка, слепок не
# изменится никогда, и Caddy навсегда останется со старым конфигом в памяти.
# Безусловный reload такого состояния не допускает: неизменный конфиг Caddy
# распознаёт сам и ничего не делает.
echo "перечитываю конфигурацию Caddy"
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null \
  || compose up -d --force-recreate caddy

printf '%s\n' "$revision" > "$ROOT/.deployed"
docker image prune -f > /dev/null

# ── 5. Проверка — отсюда, а не снаружи ───────────────────────────────────────
# Раннер GitHub до этого сервера не достучится, поэтому единственная надёжная
# проверка живости — локальная. В журнале systemd она и остаётся.
#
# Спрашиваем сам core-api изнутри его контейнера, а не Caddy снаружи. Caddy
# отдаёт сайт только для своего домена, и запрос на 127.0.0.1 в этот блок
# не попадёт вовсе; вдобавок на первом деплое сертификата ещё нет. А отвалиться
# после обновления скорее всего может именно приложение — на миграциях или на
# подключении к базе.
healthy=нет
for attempt in $(seq 1 20); do
  if compose exec -T core-api python -c \
       "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" \
       > /dev/null 2>&1; then
    healthy=да
    break
  fi
  sleep 3
done

if [ "$healthy" != да ]; then
  echo "выложено $revision, но core-api не отвечает — docker compose -f $COMPOSE_FILE logs core-api" >&2
  exit 1
fi

# Публичный адрес проверяется отдельно и не влияет на исход: он зависит от
# выпуска сертификата, а тот — от внешнего DNS и доступности порта 80. Стенд,
# который поднялся правильно, не должен считаться сломанным из-за того, что
# Let's Encrypt ещё не ответил.
domain=$(sed -n 's/^DOMAIN=//p' "$ROOT/.env" | head -1)
if [ -n "$domain" ] && curl -fsS --max-time 10 --resolve "$domain:443:127.0.0.1" \
     "https://$domain/health" > /dev/null 2>&1; then
  echo "выложено $revision, стенд отвечает на https://$domain"
else
  echo "выложено $revision, core-api жив; публичный адрес ещё не отвечает"
fi
