# Multi-stage build для Telegram Mini App (React)
FROM public.ecr.aws/docker/library/node:18-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

ARG PUBLIC_URL=/miniapp
ARG REACT_APP_API_URL=/api
ARG REACT_APP_TELEGRAM_BOT_USERNAME=
ARG REACT_APP_YANDEX_MAPS_API_KEY=
ARG REACT_APP_PUBLIC_ORIGIN=
ENV PUBLIC_URL=${PUBLIC_URL}
ENV REACT_APP_API_URL=${REACT_APP_API_URL}
ENV REACT_APP_TELEGRAM_BOT_USERNAME=${REACT_APP_TELEGRAM_BOT_USERNAME}
ENV REACT_APP_YANDEX_MAPS_API_KEY=${REACT_APP_YANDEX_MAPS_API_KEY}
ENV REACT_APP_PUBLIC_ORIGIN=${REACT_APP_PUBLIC_ORIGIN}
RUN npm run build

# Production stage (см. nginx/Dockerfile — зеркало вместо docker.io при проблемах IPv6)
FROM public.ecr.aws/docker/library/nginx:alpine

COPY --from=build /app/build /usr/share/nginx/html

# SPA: /miniapp/ отдаём через alias из корня сборки
RUN echo 'server {' > /etc/nginx/conf.d/default.conf && \
    echo '    listen 80;' >> /etc/nginx/conf.d/default.conf && \
    echo '    server_name localhost;' >> /etc/nginx/conf.d/default.conf && \
    echo '    root /usr/share/nginx/html;' >> /etc/nginx/conf.d/default.conf && \
    echo '    index index.html;' >> /etc/nginx/conf.d/default.conf && \
    echo '    location /miniapp { return 301 /miniapp/; }' >> /etc/nginx/conf.d/default.conf && \
    echo '    location /miniapp/ {' >> /etc/nginx/conf.d/default.conf && \
    echo '        alias /usr/share/nginx/html/;' >> /etc/nginx/conf.d/default.conf && \
    echo '        index index.html;' >> /etc/nginx/conf.d/default.conf && \
    echo '        try_files $uri $uri/ /index.html;' >> /etc/nginx/conf.d/default.conf && \
    echo '    }' >> /etc/nginx/conf.d/default.conf && \
    echo '    location / { try_files $uri $uri/ /index.html; }' >> /etc/nginx/conf.d/default.conf && \
    echo '}' >> /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
