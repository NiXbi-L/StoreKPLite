FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic python-multipart

COPY bot_api_service /app/bot_api_service

ENV PYTHONUNBUFFERED=1
EXPOSE 8010

CMD ["uvicorn", "bot_api_service.main:app", "--host", "0.0.0.0", "--port", "8010"]
