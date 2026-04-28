FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY bot_tg/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .
CMD ["python", "-m", "bot_tg.main"]
