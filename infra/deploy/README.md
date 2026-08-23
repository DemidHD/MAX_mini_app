# Выкладка на стенд

Сервер сам проверяет реестр и обновляется. Снаружи в него никто не стучится.

## Почему так, а не по SSH

Входящий SSH с раннеров GitHub до этого сервера не доходит. Проверено пробой
`Диагностика SSH` на четырёх сочетаниях: порты 22 и 2222, полный и урезанный
набор алгоритмов. Везде одинаково — TCP устанавливается, баннер сервера
приходит, а на первом же пакете обмена ключами наступает тишина до таймаута.

Это исключает и фильтр по номеру порта, и потерю крупных пакетов: урезанный
набор ужимает `KEXINIT` примерно до трёхсот байт, и он не проходит так же.
Направление «сервер наружу» при этом рабочее. Подробнее — решение Р71
в [`DECISIONS.md`](../../DECISIONS.md).

## Как это работает

1. CI собирает образы и кладёт их в GHCR с тегом коммита и `latest`.
   В образ проставляется метка `org.opencontainers.image.revision`.
   Образов четыре: три сервиса и свой Caddy — официальный собран без
   DNS-плагинов, а без плагина Cloudflare не работает `dns-01`.
2. Таймер systemd раз в минуту запускает `update.sh` на сервере.
3. Скрипт забирает манифест `core:latest` и читает из метки коммит.
   Если коммит тот же и все сервисы живы — выходит, ничего не делая.
4. Иначе скачивает `docker-compose.prod.yml` и конфигурацию Caddy **того же
   коммита**, поднимает стек с `IMAGE_TAG` равным этому коммиту и проверяет
   `/health` изнутри сервера.

Проверка живости делается на сервере, а не в workflow, по той же причине,
по которой выкладка перевёрнута: раннер до стенда не достучится.

## Что нужно завести в Cloudflare

Сертификат выпускается испытанием `dns-01`: владение доменом подтверждается
временной записью в DNS, а не ответом на входящее подключение. Из-за этого
Cloudflare здесь не «ещё один сервис», а обязательная часть — без токена Caddy
не поднимется.

**1. Домен в Cloudflare.** Добавить `studmap.ru` как зону (тариф Free
достаточен) и переключить NS-серверы у регистратора на выданные Cloudflare.
Пока NS не переключены, Cloudflare зоной не управляет и `dns-01` работать
не будет.

**2. A-запись** `@` → `5.42.122.80`. Режим — **DNS only** (серое облако), а не
Proxied. Проксирование пустило бы трафик через Cloudflare, а это отдельное
решение с другими последствиями; сейчас нужен только DNS.

**3. API-токен.** Profile → API Tokens → Create Token → Custom token.
Права ровно два, больше не нужно и давать не надо:

| Раздел | Ресурс | Право |
|---|---|---|
| Zone | Zone | Read |
| Zone | DNS | Edit |

Zone Resources — ограничить конкретной зоной `studmap.ru`, а не «all zones».
Токен показывается один раз, при создании.

**4. Положить токен на сервер.** Он живёт только в `/opt/navigator/.env`
и больше нигде: в репозиторий не попадает, в секреты GitHub тоже не нужен —
выкладка сертификатами не занимается.

```bash
echo 'CLOUDFLARE_API_TOKEN=<токен>' >> /opt/navigator/.env
chmod 600 /opt/navigator/.env
```

## Переменные стенда

Всё это лежит в `/opt/navigator/.env`. Выкладка этот файл не трогает.

| Переменная | Что это | Без неё |
|---|---|---|
| `DOMAIN` | домен стенда | Caddy не поднимется |
| `CLOUDFLARE_API_TOKEN` | токен с правом менять записи зоны | Caddy не поднимется |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | доступ к базе | не поднимется ничего |
| `ADMIN_PASSWORD` | пароль админки | не поднимется ничего |

Остальные переменные из `.env.example` имеют разумные значения по умолчанию
прямо в `docker-compose.prod.yml` и задаются только при необходимости.

## Установка

Один раз, под root. Дальше всё само.

```bash
# 1. Каталог и конфигурация стенда должны уже существовать:
#    /opt/navigator/.env — переменные из таблицы выше.

# 2. Скрипт обновления
curl -fsSL https://raw.githubusercontent.com/Danil-prog-coder/MAX_mini_app/main/infra/deploy/update.sh \
  -o /opt/navigator/update.sh
chmod +x /opt/navigator/update.sh

# 3. Юниты systemd
curl -fsSL https://raw.githubusercontent.com/Danil-prog-coder/MAX_mini_app/main/infra/deploy/navigator-update.service \
  -o /etc/systemd/system/navigator-update.service
curl -fsSL https://raw.githubusercontent.com/Danil-prog-coder/MAX_mini_app/main/infra/deploy/navigator-update.timer \
  -o /etc/systemd/system/navigator-update.timer

systemctl daemon-reload
systemctl enable --now navigator-update.timer
```

## Проверить

```bash
systemctl start navigator-update      # выложить прямо сейчас, не дожидаясь таймера
journalctl -u navigator-update -f     # что происходит
systemctl list-timers navigator-update
cat /opt/navigator/.deployed          # какой коммит выложен
```

## Откат

Тег образа — SHA коммита, поэтому откат это запуск с прежним значением:

```bash
cd /opt/navigator
export IMAGE_TAG=<коммит, на который откатываемся>
docker compose -f docker-compose.prod.yml up -d
```

Таймер вернёт стенд к последней сборке при следующей проверке, поэтому на
время разбирательства его стоит остановить: `systemctl stop navigator-update.timer`.

## Обновление самого скрипта

`update.sh` лежит на сервере и сам себя не обновляет — намеренно: скрипт,
переписывающий себя во время работы, чинится тяжело. Если он изменился
в репозитории, повторите шаг 2 установки.
