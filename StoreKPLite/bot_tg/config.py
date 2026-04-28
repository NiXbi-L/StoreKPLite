"""Конфиг бота (переменные окружения)."""
from os import getenv

BOT_TOKEN = getenv("BOT_TOKEN")
# API_BASE_URL можно задавать со слэшем в конце или без — rstrip убирает дубли
_API_BASE = (getenv("API_BASE_URL") or "http://localhost:80").rstrip("/")
USERS_SERVICE_URL = getenv("USERS_SERVICE_URL") or f"{_API_BASE}/api/users"
INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "")

OWNER_ID = int(getenv("OWNER_ID", "1660528172"))

def get_set_phone_url() -> str:
    base = USERS_SERVICE_URL.rstrip("/")
    return f"{base}/internal/set-phone-by-telegram"
