#!/bin/sh
# Подставляет из API_BASE_URL: Referer, канонический хост (редиректы), server_name, путь к live-сертификату.
set -eu
# В образе nginx access.log по умолчанию — symlink на /dev/stdout; общий том не даёт читать лог из users-service.
# Пишем в реальный файл в shared/ (тот же том nginx_access_logs:/var/log/nginx).
mkdir -p /var/log/nginx/shared
if [ -L /var/log/nginx/shared/access.log ]; then
  rm -f /var/log/nginx/shared/access.log
fi
if [ ! -f /var/log/nginx/shared/access.log ]; then
  touch /var/log/nginx/shared/access.log
fi
chown nginx:nginx /var/log/nginx/shared/access.log 2>/dev/null || chmod 666 /var/log/nginx/shared/access.log 2>/dev/null || true

# docker-compose.loadtest-nginx.yml монтирует готовый nginx.conf поверх — не перезаписываем
if [ "${NGINX_USE_MOUNTED_CONF:-}" = "1" ]; then
  exec nginx -g 'daemon off;'
fi
b="${API_BASE_URL:-}"
b="${b%/}"
if [ -z "$b" ]; then
  echo "nginx: API_BASE_URL пуст — для Referer используется https://127.0.0.1; задайте API_BASE_URL в .env" >&2
  b="https://127.0.0.1"
fi
case "$b" in
  http://*|https://*) ;;
  *) b="https://$b" ;;
esac
scheme="${b%%://*}"
rest="${b#*://}"
hostport="${rest%%/*}"
hostport_esc=$(printf '%s' "$hostport" | sed 's/\./\\./g')
export NGINX_REFERER_MAP_PATTERN="^${scheme}://${hostport_esc}/"
export NGINX_CANONICAL_HOST="$hostport"
# Имя каталога в /etc/letsencrypt/live/ (первое -d у certbot). Переопределите, если отличается от хоста в API_BASE_URL.
export NGINX_SSL_LIVE_DIR="${NGINX_SSL_LIVE_DIR:-$hostport}"
# Основной server_name; при откате на miniapp.nixbi.ru — только он (без www.miniapp…).
# При новом домене: apex + www.
if [ "$hostport" = "miniapp.nixbi.ru" ]; then
  export NGINX_LEGACY_SERVER_NAMES=""
  export NGINX_PRIMARY_SERVER_NAMES="${NGINX_PRIMARY_SERVER_NAMES:-$hostport}"
else
  export NGINX_LEGACY_SERVER_NAMES="${NGINX_LEGACY_SERVER_NAMES:-miniapp.nixbi.ru}"
  export NGINX_PRIMARY_SERVER_NAMES="${NGINX_PRIMARY_SERVER_NAMES:-$hostport www.$hostport}"
fi

# Пока нет live/<домен>/ после смены API_BASE_URL — не падаем: берём старый сертификат, поднимаем :80 для certbot.
_live="/etc/letsencrypt/live/${NGINX_SSL_LIVE_DIR}"
if [ ! -r "${_live}/fullchain.pem" ] && [ -r "/etc/letsencrypt/live/miniapp.nixbi.ru/fullchain.pem" ]; then
  echo "nginx: нет ${_live}/fullchain.pem — временно используем miniapp.nixbi.ru; после certbot перезапустите контейнер" >&2
  export NGINX_SSL_LIVE_DIR="miniapp.nixbi.ru"
fi

_tpl_work="/tmp/nginx.conf.template.work"
cp /etc/nginx/nginx.conf.template "$_tpl_work"
if [ -z "${NGINX_BOT_API_PROXY_PASS:-}" ]; then
  echo "nginx: NGINX_BOT_API_PROXY_PASS пуст — блок /bot-api/ отключён (задайте URL bridge, иначе POST /bot-api/* уйдёт в миниапп и даст 405)" >&2
  sed -i '/##BEGIN_BOT_API_PROXY##/,/##END_BOT_API_PROXY##/d' "$_tpl_work"
  envsubst '${NGINX_REFERER_MAP_PATTERN}${NGINX_CANONICAL_HOST}${NGINX_PRIMARY_SERVER_NAMES}${NGINX_SSL_LIVE_DIR}${NGINX_LEGACY_SERVER_NAMES}' < "$_tpl_work" > /etc/nginx/nginx.conf
else
  export NGINX_BOT_API_PROXY_PASS
  envsubst '${NGINX_REFERER_MAP_PATTERN}${NGINX_CANONICAL_HOST}${NGINX_PRIMARY_SERVER_NAMES}${NGINX_SSL_LIVE_DIR}${NGINX_LEGACY_SERVER_NAMES}${NGINX_BOT_API_PROXY_PASS}' < "$_tpl_work" > /etc/nginx/nginx.conf
fi
rm -f "$_tpl_work"

if [ -z "$NGINX_LEGACY_SERVER_NAMES" ]; then
  sed -i '/##BEGIN_LEGACY_REDIRECT##/,/##END_LEGACY_REDIRECT##/d' /etc/nginx/nginx.conf
else
  sed -i '/##BEGIN_LEGACY_REDIRECT##/d; /##END_LEGACY_REDIRECT##/d' /etc/nginx/nginx.conf
fi

exec nginx -g 'daemon off;'
