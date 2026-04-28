"""При добавлении бота в группу или канал — отправить владельцу (OWNER_ID) ID чата."""
import logging
from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import ChatMemberUpdated

from bot_tg.config import OWNER_ID

logger = logging.getLogger(__name__)
router = Router(name="added_to_chat")


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_chat(event: ChatMemberUpdated):
    """Бот добавлен в группу/супергруппу/канал — шлём OWNER_ID id чата.
    Личные чаты (private) сюда тоже прилетают от Telegram при первом /start — не спамим владельца."""
    chat = event.chat
    if chat.type == "private":
        return
    chat_id = chat.id
    chat_type = chat.type
    title = (chat.title or "").strip() or "—"
    text = (
        f"Бот добавлен в чат.\n"
        f"Тип: <code>{chat_type}</code>\n"
        f"ID: <code>{chat_id}</code>\n"
        f"Название: {title}"
    )
    try:
        await event.bot.send_message(OWNER_ID, text)
        logger.info("Отправлен OWNER_ID id чата: %s (%s)", chat_id, title)
    except Exception as e:
        logger.exception("Не удалось отправить OWNER_ID сообщение о новом чате: %s", e)
