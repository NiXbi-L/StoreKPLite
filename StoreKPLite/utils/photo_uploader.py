"""
Утилита для автоматической загрузки фотографий в Telegram и получения file_id
"""
import logging
from pathlib import Path
import os
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.database import async_session_maker
from database.models import ItemPhoto

logger = logging.getLogger(__name__)


async def upload_photo_to_telegram(
    bot: Bot,
    photo: ItemPhoto,
    chat_id: int,
    session: AsyncSession
) -> bool:
    """
    Загружает одно фото в Telegram и сохраняет file_id
    
    Args:
        bot: Экземпляр бота
        photo: Объект фото из БД
        chat_id: ID чата/группы для отправки
        session: Сессия БД
    
    Returns:
        True если успешно, False если ошибка
    """
    try:
        # Пробуем разные варианты путей
        # В БД путь хранится как /uploads/items/filename.jpg
        # Нужно найти реальный файл в файловой системе
        
        filename = os.path.basename(photo.file_path)  # Получаем имя файла (например, 1_1.jpg)
        tried_paths = []
        photo_path = None
        
        # Список возможных путей для поиска
        possible_paths = [
            f"/app/uploads/items/{filename}",  # Docker контейнер
            f"uploads/items/{filename}",  # Относительный путь
            os.path.join(os.getcwd(), "uploads/items", filename),  # Относительно рабочей директории
            photo.file_path.lstrip("/"),  # Путь из БД без ведущего /
            f"/app/{photo.file_path.lstrip('/')}",  # /app + путь из БД
        ]
        
        # Пробуем каждый путь
        for path_str in possible_paths:
            photo_path = Path(path_str)
            tried_paths.append(str(photo_path))
            if photo_path.exists():
                logger.debug(f"Файл найден: {photo_path}")
                break
        
        # Если файл не найден стандартными путями, делаем рекурсивный поиск
        if not photo_path or not photo_path.exists():
            # Дополнительно проверяем, существует ли директория uploads/items
            uploads_dir = Path("/app/uploads/items")
            if not uploads_dir.exists():
                logger.warning(f"Директория {uploads_dir} не существует. Пытаюсь создать...")
                try:
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Директория {uploads_dir} создана")
                except Exception as e:
                    logger.error(f"Не удалось создать директорию {uploads_dir}: {e}")
            
            # Пробуем найти файл рекурсивно в /app
            app_dir = Path("/app")
            if app_dir.exists():
                try:
                    logger.info(f"🔍 Ищу файл '{filename}' рекурсивно в /app...")
                    found_files = list(app_dir.rglob(filename))
                    if found_files:
                        photo_path = found_files[0]
                        logger.info(f"✅ Файл найден в альтернативном месте: {photo_path}")
                    else:
                        logger.warning(f"❌ Файл '{filename}' не найден ни в одном месте в /app")
                        
                        # Если файл не найден по точному имени, пробуем найти по item_id
                        # Это может помочь, если файл был переименован
                        if uploads_dir.exists() and photo.item_id:
                            logger.info(f"🔍 Пробую найти файл по item_id={photo.item_id}...")
                            # Ищем все файлы, начинающиеся с item_id
                            pattern = f"{photo.item_id}_*"
                            matching_files = list(uploads_dir.glob(pattern))
                            if matching_files:
                                # Берем первый найденный файл для этого item_id
                                photo_path = matching_files[0]
                                logger.info(f"✅ Найден альтернативный файл для item_id={photo.item_id}: {photo_path}")
                                # Обновляем путь в БД, чтобы в следующий раз найти сразу
                                await session.execute(
                                    update(ItemPhoto)
                                    .where(ItemPhoto.id == photo.id)
                                    .values(file_path=f"/uploads/items/{photo_path.name}")
                                )
                                await session.commit()
                            else:
                                logger.warning(f"❌ Файлы для item_id={photo.item_id} не найдены")
                        
                        # Логируем содержимое возможных директорий для отладки
                        if Path("/app/uploads").exists():
                            logger.debug(f"Содержимое /app/uploads: {list(Path('/app/uploads').iterdir())}")
                        if Path("/app/uploads/items").exists():
                            all_files = list(Path('/app/uploads/items').iterdir())
                            logger.debug(f"Содержимое /app/uploads/items ({len(all_files)} файлов): {[f.name for f in all_files[:10]]}")
                except Exception as e:
                    logger.error(f"Ошибка при рекурсивном поиске файла: {e}", exc_info=True)
            
            if not photo_path or not photo_path.exists():
                logger.warning(
                    f"❌ Файл не найден: {photo.file_path}\n"
                    f"Имя файла: {filename}\n"
                    f"Пробовал пути: {', '.join(set(tried_paths))}\n"
                    f"Текущая рабочая директория: {os.getcwd()}"
                )
                return False
        
        # Отправляем фото с подписью для идентификации
        # Используем FSInputFile для отправки файла (нужна строка пути)
        input_file = FSInputFile(str(photo_path))
        sent_message = await bot.send_photo(
            chat_id=chat_id,
            photo=input_file,
            caption=f"photo_id:{photo.id}"
        )
        
        # Получаем file_id из отправленного сообщения
        if sent_message.photo:
            # Берем самое большое фото
            largest_photo = max(sent_message.photo, key=lambda p: p.file_size if p.file_size else 0)
            file_id = largest_photo.file_id
            
            # Сохраняем file_id в БД
            await session.execute(
                update(ItemPhoto)
                .where(ItemPhoto.id == photo.id)
                .values(telegram_file_id=file_id)
            )
            await session.commit()
            logger.info(f"✅ File ID сохранен для фото #{photo.id}")
            return True
        else:
            logger.error(f"❌ Не удалось получить фото из сообщения для photo_id={photo.id}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке фото {photo.id}: {e}", exc_info=True)
        return False


async def upload_all_photos_without_file_id(
    bot: Bot,
    chat_id: int,
    limit: Optional[int] = None
) -> tuple[int, int]:
    """
    Загружает все фотографии без file_id в Telegram
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата/группы для отправки
        limit: Максимальное количество фото для загрузки (None = все)
    
    Returns:
        Кортеж (загружено, ошибок)
    """
    async with async_session_maker() as session:
        # Получаем все фотографии без telegram_file_id
        query = select(ItemPhoto).where(ItemPhoto.telegram_file_id.is_(None))
        if limit:
            query = query.limit(limit)
        
        result = await session.execute(query)
        photos = result.scalars().all()
        
        if not photos:
            logger.info("✅ Все фотографии уже загружены в Telegram")
            return 0, 0
        
        logger.info(f"📤 Начинаю загрузку {len(photos)} фотографий...")
        
        uploaded = 0
        failed = 0
        skipped = 0  # Пропущено из-за отсутствия файлов
        
        for photo in photos:
            # Проверяем, существует ли файл перед попыткой загрузки
            filename = os.path.basename(photo.file_path)
            possible_paths = [
                Path(f"/app/uploads/items/{filename}"),
                Path(f"uploads/items/{filename}"),
                Path(os.path.join(os.getcwd(), "uploads/items", filename)),
            ]
            
            file_exists = False
            for path in possible_paths:
                if path.exists():
                    file_exists = True
                    break
            
            # Если файл не найден, пробуем найти по item_id
            if not file_exists:
                uploads_dir = Path("/app/uploads/items")
                if uploads_dir.exists() and photo.item_id:
                    pattern = f"{photo.item_id}_*"
                    matching_files = list(uploads_dir.glob(pattern))
                    if matching_files:
                        file_exists = True
                        # Обновляем путь в БД
                        await session.execute(
                            update(ItemPhoto)
                            .where(ItemPhoto.id == photo.id)
                            .values(file_path=f"/uploads/items/{matching_files[0].name}")
                        )
                        await session.commit()
                        logger.info(f"✅ Найден альтернативный файл для фото {photo.id}, путь обновлен")
            
            if not file_exists:
                logger.warning(
                    f"⏭️ Пропускаю фото {photo.id} (item_id={photo.item_id}): "
                    f"файл '{filename}' не найден в файловой системе"
                )
                skipped += 1
                continue
            
            success = await upload_photo_to_telegram(bot, photo, chat_id, session)
            if success:
                uploaded += 1
            else:
                failed += 1
        
        logger.info(
            f"✅ Загрузка завершена! Загружено: {uploaded}, Ошибок: {failed}, Пропущено: {skipped}"
        )
        
        return uploaded, failed


async def upload_specific_photo(
    photo_id: int,
    bot: Bot,
    chat_id: int
) -> bool:
    """
    Загружает конкретное фото по ID
    
    Args:
        photo_id: ID фото в БД
        bot: Экземпляр бота
        chat_id: ID чата/группы для отправки
    
    Returns:
        True если успешно, False если ошибка
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemPhoto).where(ItemPhoto.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        
        if not photo:
            logger.error(f"Фото с ID {photo_id} не найдено")
            return False
        
        if photo.telegram_file_id:
            logger.info(f"Фото {photo_id} уже имеет file_id")
            return True
        
        return await upload_photo_to_telegram(bot, photo, chat_id, session)

