"""
Точка входа Telegram-бота Timoshka Store.

Сейчас бот не авторизует пользователя в API магазина: только принимает контакт и шлёт номер
в users-service (internal/set-phone-by-telegram). Вход в магазин и JWT — в мини-приложении.

Запуск: python -m bot_tg.main (из корня проекта) или с указанием PYTHONPATH.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# корень проекта в PYTHONPATH
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot_tg.config import BOT_TOKEN
from bot_tg.handlers import added_to_chat, contact, start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(added_to_chat.router)
    dp.include_router(contact.router)
    dp.include_router(start.router)

    logger.info("Бот запущен (@%s)", os.getenv("TELEGRAM_BOT_USERNAME", "bot"))
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")