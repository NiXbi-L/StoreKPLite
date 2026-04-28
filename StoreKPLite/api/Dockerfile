# Без «# syntax=docker/dockerfile:…» — иначе BuildKit тянет образ с Docker Hub (на хостах без IPv6/маршрута к Hub сборка падает).
# Базовый образ — AWS Public ECR (зеркало library/*), иначе metadata с registry-1.docker.io часто уходит в недоступный IPv6.
# Кэш pip между сборками (BuildKit): RUN --mount=type=cache поддерживается встроенным фронтендом современного Docker.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Установка системных зависимостей (gcc для компиляции; fonts-dejavu-core для кириллицы в PDF)
RUN apt-get update --quiet --quiet && \
    DEBIAN_FRONTEND=noninteractive apt-get install --yes --quiet --quiet --no-install-recommends \
    gcc \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Копирование файла зависимостей
COPY requirements.txt .

# Установка Python зависимостей (wheels в BuildKit cache — не раздуваем слой образа)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов проекта
COPY . .

# Команда по умолчанию (будет переопределена в docker-compose.yml)
CMD ["python", "-m", "api.users.main"]

