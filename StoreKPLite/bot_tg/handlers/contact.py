"""Обработка расшаривания контакта (номер телефона)."""
import logging
import httpx
from aiogram import Router
from aiogram.types import Message

from bot_tg.config import get_set_phone_url, INTERNAL_TOKEN

logger = logging.getLogger(__name__)
router = Router(name="contact")


@router.message(lambda m: m.contact is not None)
async def handle_contact(message: Message):
    """Пользователь поделился контактом — отправляем номер в users-service и подтверждаем."""
    contact = message.contact
    phone = (contact.phone_number or "").strip()
    if not phone:
        await message.answer("Не удалось получить номер. Попробуйте ещё раз.")
        return

    telegram_id = message.from_user.id if message.from_user else contact.user_id
    if not telegram_id:
        await message.answer("Ошибка: не определён пользователь.")
        return

    url = get_set_phone_url()
    headers = {"Content-Type": "application/json", "X-Internal-Token": INTERNAL_TOKEN}
    payload = {"telegram_id": telegram_id, "phone_number": phone}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code == 200:
            await message.answer("Номер сохранён. Можете вернуться в приложение.")
        elif r.status_code == 404:
            await message.answer(
                "Сначала откройте мини-приложение из меню бота и войдите в аккаунт, "
                "затем снова нажмите «Поделиться номером».\n\n"
                "Вопросы и контакты: https://t.me/MatchWear_chine"
            )
        else:
            logger.warning("set-phone-by-telegram %s: %s", r.status_code, r.text)
            await message.answer("Не удалось сохранить номер. Попробуйте позже.")
    except Exception as e:
        logger.exception("Request to users-service failed: %s", e)
        await message.answer("Ошибка связи с сервером. Попробуйте позже.")
