FROM nginx:1.27-alpine

# openssl — только для генерации запасного самоподписанного сертификата
# (docker-entrypoint.d/10-ensure-tls-cert.sh), когда настоящий не подключён.
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/nginx.conf
COPY docker-entrypoint.d/10-ensure-tls-cert.sh /docker-entrypoint.d/10-ensure-tls-cert.sh
RUN chmod +x /docker-entrypoint.d/10-ensure-tls-cert.sh
