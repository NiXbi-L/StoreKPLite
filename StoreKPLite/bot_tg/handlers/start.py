"""Команда /start и приветствие. Deep link: ?startapp=share_phone — сразу кнопка «Поделиться номером»."""
import logging
import re

import httpx
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from bot_tg.config import INTERNAL_TOKEN, USERS_SERVICE_URL

logger = logging.getLogger(__name__)
router = Router(name="start")

# Параметр из ссылки: https://t.me/{TELEGRAM_BOT_USERNAME}?startapp=share_phone
START_PAYLOAD_SHARE_PHONE = "share_phone"
# Вход из браузера: https://t.me/bot?start=weblogin_<32 hex>
START_BROWSER_LOGIN_PREFIX = "weblogin_"
_BROWSER_CODE_RE = re.compile(r"^[a-f0-9]{32}$")

PHONE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Поделиться номером", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    """
    Обработка /start. Если перешли по ссылке с ?startapp=share_phone — сразу показываем кнопку номера.
    """
    args = (command.args or "").strip()
    if args.startswith(START_BROWSER_LOGIN_PREFIX):
        code = args[len(START_BROWSER_LOGIN_PREFIX) :].strip()
        if not _BROWSER_CODE_RE.match(code):
            await message.answer("Ссылка входа недействительна. Закройте страницу и откройте вход в приложении заново.")
            return
        uid = message.from_user.id if message.from_user else None
        if not uid:
            await message.answer("Не удалось определить аккаунт Telegram.")
            return
        url = f"{USERS_SERVICE_URL.rstrip('/')}/internal/browser-login/confirm"
        headers = {"Content-Type": "application/json", "X-Internal-Token": INTERNAL_TOKEN}
        payload = {
            "code": code,
            "telegram_id": uid,
            "first_name": message.from_user.first_name if message.from_user else None,
            "username": message.from_user.username if message.from_user else None,
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(url, json=payload, headers=headers)
        except Exception as e:
            logger.exception("browser-login confirm request failed: %s", e)
            await message.answer("Не удалось связаться с сервером. Попробуйте позже.")
            return
        if r.status_code == 404:
            await message.answer("Код входа устарел или уже использован. Вернитесь на страницу входа и получите новую ссылку.")
            return
        if r.status_code == 409:
            await message.answer("Этот код входа уже обработан. Вернитесь в браузер.")
            return
        if r.status_code != 200:
            logger.warning("browser-login confirm %s: %s", r.status_code, r.text)
            await message.answer("Не удалось подтвердить вход. Попробуйте ещё раз или запросите новую ссылку.")
            return
        try:
            data = r.json()
        except Exception:
            data = {}
        if data.get("status") == "forbidden":
            await message.answer(
                "Сейчас вход в приложение из браузера доступен только администраторам. "
                "Откройте магазин через Telegram."
            )
            return
        await message.answer("Вход подтверждён. Вернитесь в браузер — страница обновится сама.")
        return
    if args == START_PAYLOAD_SHARE_PHONE:
        text = (
            "Укажите или измените номер телефона для профиля приложения.\n\n"
            "Нажмите кнопку ниже, затем вернитесь в мини-приложение — номер сохранится."
        )
        await message.answer(text, reply_markup=PHONE_KEYBOARD)
        return
    text = (
        "Привет! Я бот MatchWear.\n\n"
        "Весь магазин — в мини-приложении: нажми «Открыть приложение» или меню у этого бота. "
        "Заказы смотри в приложении: Профиль → заказы.\n\n"
        "Вопросы и контакты — в канале https://t.me/MatchWear_chine"
    )
    await message.answer(text)


@router.message(F.text)
async def any_text(message: Message):
    """На любое текст — подсказка и кнопка «Поделиться номером»."""
    text = (
        "Нажмите кнопку «Поделиться номером», чтобы сохранить номер в профиле мини-приложения.\n\n"
        "Магазин и заказы — в приложении MatchWear. Вопросы — https://t.me/MatchWear_chine"
    )
    await message.answer(text, reply_markup=PHONE_KEYBOARD)
