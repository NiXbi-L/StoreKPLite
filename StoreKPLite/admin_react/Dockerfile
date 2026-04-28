# Multi-stage build для React приложения
FROM public.ecr.aws/docker/library/node:18-alpine as build

WORKDIR /app

# Копируем package files (включая package-lock.json если есть)
COPY package*.json ./

# Устанавливаем зависимости
# Используем npm ci для более стабильных сборок (требует package-lock.json)
RUN npm ci

# Копируем исходный код
COPY . .

# Собираем приложение с PUBLIC_URL и API_URL для правильных путей
# PUBLIC_URL может быть /admin или /<секретный_путь>/admin для скрытия админки
ARG PUBLIC_URL=/admin
ARG REACT_APP_API_URL=/api
ENV PUBLIC_URL=${PUBLIC_URL}
ENV REACT_APP_API_URL=${REACT_APP_API_URL}
# Без .map в проде: в Sources не подтягиваются исходники TS/TSX по клику
ENV GENERATE_SOURCEMAP=false
RUN npm run build

# Production stage (см. nginx/Dockerfile — зеркало вместо docker.io при проблемах IPv6)
FROM public.ecr.aws/docker/library/nginx:alpine

# Копируем собранное приложение
COPY --from=build /app/build /usr/share/nginx/html

# Создаем nginx конфигурацию для SPA (префикс из PUBLIC_URL)
ARG PUBLIC_URL=/admin
RUN P="${PUBLIC_URL}" && \
    echo "server {" > /etc/nginx/conf.d/default.conf && \
    echo "    listen 80;" >> /etc/nginx/conf.d/default.conf && \
    echo "    server_name localhost;" >> /etc/nginx/conf.d/default.conf && \
    echo "    root /usr/share/nginx/html;" >> /etc/nginx/conf.d/default.conf && \
    echo "    index index.html;" >> /etc/nginx/conf.d/default.conf && \
    echo "    location ~ ^${P}/(static|favicon\\.ico|logo.*\\.png|manifest\\.json|asset-manifest\\.json) {" >> /etc/nginx/conf.d/default.conf && \
    echo "        rewrite ^${P}/(.*)\$ /\$1 break;" >> /etc/nginx/conf.d/default.conf && \
    echo "    }" >> /etc/nginx/conf.d/default.conf && \
    echo "    location ${P}/ {" >> /etc/nginx/conf.d/default.conf && \
    echo "        try_files \$uri \$uri/ ${P}/index.html;" >> /etc/nginx/conf.d/default.conf && \
    echo "    }" >> /etc/nginx/conf.d/default.conf && \
    echo "    location = ${P}/index.html {" >> /etc/nginx/conf.d/default.conf && \
    echo "        rewrite ^${P}/index.html\$ /index.html break;" >> /etc/nginx/conf.d/default.conf && \
    echo "    }" >> /etc/nginx/conf.d/default.conf && \
    echo "    location / { try_files \$uri \$uri/ /index.html; }" >> /etc/nginx/conf.d/default.conf && \
    echo "}" >> /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

