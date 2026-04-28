"""
Утилиты для работы с медиагруппами и отправкой вещей
"""
from aiogram.types import InputMediaPhoto
from typing import List, Optional
from database.models import Item, ItemPhoto, ItemPriceHistory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from utils.exchange_rate import calculate_item_price
from datetime import datetime, timedelta


async def prepare_item_media_group(
    item: Item,
    session: AsyncSession,
    include_description: bool = True
) -> List[InputMediaPhoto]:
    """
    Подготавливает медиагруппу для отправки вещи
    
    Args:
        item: Объект вещи из БД
        session: Сессия БД
        include_description: Включать ли описание в первую фотографию
    
    Returns:
        Список InputMediaPhoto для отправки медиагруппы
    """
    # Получаем фотографии вещи
    photos_result = await session.execute(
        select(ItemPhoto).where(ItemPhoto.item_id == item.id).order_by(ItemPhoto.id)
    )
    photos = photos_result.scalars().all()
    
    if not photos:
        return []
    
    media = []
    
    # Формируем описание для первой фотографии
    caption_parts = []
    if include_description:
        caption_parts.append(f"<b>{item.name}</b>")
        caption_parts.append("=" * 20)
        
        # Описание (если есть)
        if item.description:
            caption_parts.append(item.description)
            caption_parts.append("=" * 20)
        
        # Цена (рассчитываем с учетом курса)
        price = await calculate_item_price(item)
        caption_parts.append(f"💰 Цена: {price:.2f} ₽")
        
        # Размеры (если есть)
        if item.size:
            caption_parts.append(f"📏 Размеры: {item.size}")
        
        # Добавляем разделитель перед историей цены
        caption_parts.append("=" * 20)
        
        # Получаем историю цены за текущую неделю
        today = datetime.now().date()
        days_since_monday = today.weekday()
        week_start = datetime.combine(today - timedelta(days=days_since_monday), datetime.min.time())
        
        history_result = await session.execute(
            select(ItemPriceHistory).where(
                ItemPriceHistory.item_id == item.id,
                ItemPriceHistory.week_start == week_start
            )
        )
        price_history = history_result.scalar_one_or_none()
        
        if price_history:
            caption_parts.append("📊 История цены на этой неделе")
            caption_parts.append(f"📈 Макс: {float(price_history.max_price):.2f} ₽")
            caption_parts.append(f"📉 Мин: {float(price_history.min_price):.2f} ₽")
    
    caption = "\n".join(caption_parts) if caption_parts else None
    
    # Добавляем фотографии в медиагруппу
    for i, photo in enumerate(photos):
        if not photo.telegram_file_id:
            # Если нет file_id, используем file_path (но это будет медленнее)
            # В идеале нужно сначала загрузить фото в Telegram и получить file_id
            continue
        
        if i == 0:
            # В первую фотографию добавляем описание
            media.append(
                InputMediaPhoto(
                    media=photo.telegram_file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            )
        else:
            # Остальные фотографии без описания
            media.append(
                InputMediaPhoto(
                    media=photo.telegram_file_id
                )
            )
    
    return media


async def get_item_media_group(
    item_id: int,
    session: AsyncSession,
    include_description: bool = True
) -> List[InputMediaPhoto]:
    """
    Получает медиагруппу для вещи по ID
    
    Args:
        item_id: ID вещи
        session: Сессия БД
        include_description: Включать ли описание в первую фотографию
    
    Returns:
        Список InputMediaPhoto для отправки медиагруппы
    """
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        return []
    
    return await prepare_item_media_group(item, session, include_description)

