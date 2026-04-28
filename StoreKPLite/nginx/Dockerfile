# Образ nginx с нашим конфигом внутри (не зависит от volume при деплое)
# public.ecr.aws — зеркало library/*; обходит сбои IPv6 к registry-1.docker.io на части VPS
FROM public.ecr.aws/docker/library/nginx:alpine

# Удаляем дефолтный server, чтобы не было root /usr/share/nginx/html и 404 по /miniapp/
RUN rm -f /etc/nginx/conf.d/default.conf

# envsubst для подстановки Referer из API_BASE_URL при старте
RUN apk add --no-cache openssl gettext && \
    mkdir -p /etc/nginx/ssl \
      /etc/letsencrypt/live/miniapp.nixbi.ru \
      /etc/letsencrypt/live/matchwear.ru && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/privkey.pem -out /etc/nginx/ssl/fullchain.pem \
    -subj "/CN=localhost" && \
    ln -sf /etc/nginx/ssl/fullchain.pem /etc/letsencrypt/live/miniapp.nixbi.ru/fullchain.pem && \
    ln -sf /etc/nginx/ssl/privkey.pem /etc/letsencrypt/live/miniapp.nixbi.ru/privkey.pem && \
    ln -sf /etc/nginx/ssl/fullchain.pem /etc/letsencrypt/live/matchwear.ru/fullchain.pem && \
    ln -sf /etc/nginx/ssl/privkey.pem /etc/letsencrypt/live/matchwear.ru/privkey.pem

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker-entrypoint-nginx.sh /docker-entrypoint-nginx.sh
COPY inc /etc/nginx/inc
COPY errors /etc/nginx/errors
# Статика в корне канонического домена (Яндекс.Вебмастер и т.п.)
COPY static /etc/nginx/site-root-static
RUN chmod +x /docker-entrypoint-nginx.sh

ENTRYPOINT ["/docker-entrypoint-nginx.sh"]

# uploads монтируются через volume в docker-compose
# EXPOSE 80 уже есть в базовом образе
