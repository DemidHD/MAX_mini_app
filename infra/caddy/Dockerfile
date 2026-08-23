# syntax=docker/dockerfile:1
#
# Caddy с плагином Cloudflare для испытания dns-01.
#
# Официальный образ собран без DNS-плагинов, а нам нужен именно он: испытания
# `http-01` и `tls-alpn-01` требуют, чтобы Let's Encrypt подключился к серверу
# снаружи, а на этом сервере входящие соединения не доходят (решение Р71).
# `dns-01` подтверждает владение доменом записью в DNS — сервер только ходит
# наружу, к API Cloudflare, и это направление рабочее.
#
# Версия Caddy закреплена: плагин собирается против конкретного релиза, и
# «последний» здесь означал бы, что образ меняется сам по себе между сборками.

FROM caddy:2.10-builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2.10-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
