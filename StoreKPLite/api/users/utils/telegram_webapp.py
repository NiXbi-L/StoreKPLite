"""
Проверка подписи Telegram WebApp initData (для мини-приложения)
По документации: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
from urllib.parse import parse_qsl


def verify_telegram_webapp_data(init_data: str, bot_token: str) -> bool:
    """
    Проверяет валидность initData от Telegram WebApp.
    Подпись: HMAC-SHA256(data_check_string, secret_key),
    secret_key = HMAC-SHA256(bot_token, "WebAppData").
    """
    if not init_data or not bot_token:
        return False
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return False
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256,
        ).digest()
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(received_hash, expected_hash)
    except Exception:
        return False
