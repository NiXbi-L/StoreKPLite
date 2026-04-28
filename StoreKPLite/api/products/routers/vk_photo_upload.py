"""
Утилита для отправки фото в VK группу для получения attachment ID
"""
import logging
from pathlib import Path
from typing import Optional
from os import getenv
import httpx
import aiofiles

logger = logging.getLogger(__name__)

VK_API_URL = "https://api.vk.com/method"
VK_BOT_TOKEN = getenv("VK_BOT_TOKEN")
VK_USER_TOKEN = getenv("VK_USER_TOKEN")  # Токен пользователя для загрузки фото (опционально)
VK_PHOTO_GROUP_ID = getenv("VK_PHOTO_GROUP_ID")  # Формат: 200234801263 (peer_id для беседы)

def _get_group_id_from_peer_id(peer_id: str) -> Optional[int]:
    """
    Конвертировать peer_id в group_id
    peer_id для групп имеет формат: 2000000000 + group_id
    Например: 200234801263 -> 234801263
    """
    try:
        peer_id_int = int(peer_id)
        # peer_id для групп начинается с 2000000000
        if peer_id_int >= 2000000000:
            group_id = peer_id_int - 2000000000
            logger.info(f"Конвертирован peer_id {peer_id_int} в group_id {group_id}")
            return group_id
        # Если это уже group_id (без префикса), возвращаем как есть
        return peer_id_int
    except (ValueError, TypeError):
        logger.error(f"Ошибка конвертации peer_id {peer_id} в group_id")
        return None


async def upload_photo_to_vk_server(photo_path: Path) -> Optional[str]:
    """
    Загрузить фото на сервер VK и получить attachment
    
    Args:
        photo_path: Путь к файлу фото
        
    Returns:
        attachment строка (например, "photo123456_789012") или None при ошибке
    """
    # VK API не поддерживает загрузку фото через токен группы (ошибка 27)
    # Нужен токен пользователя с правами на группу
    token_to_use = VK_USER_TOKEN or VK_BOT_TOKEN
    
    if not token_to_use:
        logger.warning("Нет токена для загрузки фото в VK")
        return None
    
    try:
        # Используем photos.getWallUploadServer для загрузки фото на стену пользователя
        # Это работает с токеном пользователя и не требует album_id
        async with httpx.AsyncClient() as client:
            # Шаг 1: Получить upload_url для загрузки фото на стену
            params = {
                "access_token": token_to_use,
                "v": "5.131"
            }
            
            response = await client.get(
                f"{VK_API_URL}/photos.getWallUploadServer",
                params=params,
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                error_info = result["error"]
                error_code = error_info.get("error_code")
                if error_code == 27:  # method is unavailable with group auth
                    logger.warning(
                        "Токен группы не поддерживает загрузку фото. "
                        "Установите переменную окружения VK_USER_TOKEN с токеном пользователя."
                    )
                else:
                    logger.error(f"VK API вернул ошибку при получении upload_url: {error_info}")
                return None
            
            upload_url = result.get("response", {}).get("upload_url")
            if not upload_url:
                logger.error("Не удалось получить upload_url от VK API")
                return None
            
            # Шаг 2: Загрузить фото на сервер VK
            async with aiofiles.open(photo_path, "rb") as photo_file:
                photo_content = await photo_file.read()
                
                files = {
                    "photo": (photo_path.name, photo_content, "image/jpeg")
                }
                
                upload_response = await client.post(
                    upload_url,
                    files=files,
                    timeout=30.0
                )
                upload_response.raise_for_status()
                upload_result = upload_response.json()
                
                # Шаг 3: Сохранить фото на сервере VK
                server = upload_result.get("server")
                photo_data = upload_result.get("photo")
                hash_value = upload_result.get("hash")
                
                if not all([server, photo_data, hash_value]):
                    logger.error(f"Неполные данные после загрузки: {upload_result}")
                    return None
                
                save_params = {
                    "access_token": token_to_use,
                    "photo": photo_data,
                    "server": server,
                    "hash": hash_value,
                    "v": "5.131"
                }
                
                # Используем photos.saveWallPhoto для сохранения фото, загруженного через getWallUploadServer
                save_response = await client.get(
                    f"{VK_API_URL}/photos.saveWallPhoto",
                    params=save_params,
                    timeout=10.0
                )
                save_response.raise_for_status()
                save_result = save_response.json()
                
                if "error" in save_result:
                    logger.error(f"VK API вернул ошибку при сохранении: {save_result['error']}")
                    return None
                
                saved_photo = save_result.get("response", [])
                if not saved_photo:
                    logger.error("Не удалось сохранить фото на сервере VK")
                    return None
                
                # Формируем attachment в формате "photo{owner_id}_{photo_id}"
                photo_info = saved_photo[0]
                owner_id = photo_info.get("owner_id")
                photo_id = photo_info.get("id")
                
                if owner_id and photo_id:
                    attachment = f"photo{owner_id}_{photo_id}"
                    logger.info(f"✅ Фото успешно загружено, attachment: {attachment}")
                    return attachment
                else:
                    logger.error(f"Неполные данные сохраненного фото: {photo_info}")
                    return None
                    
    except Exception as e:
        logger.error(f"Ошибка при загрузке фото в VK: {e}", exc_info=True)
        return None


async def send_photo_to_vk_group_and_get_attachment(photo_id: int, file_path: str, skip_db_check: bool = False) -> Optional[str]:
    """
    Отправить фото в VK группу для получения attachment. Возвращает attachment или None
    
    Args:
        photo_id: ID фото в базе данных
        file_path: Путь к файлу фото
        skip_db_check: Пропустить проверку БД (используется при массовом обновлении)
        
    Returns:
        attachment строка (например, "photo123456_789012") или None
    """
    if not VK_BOT_TOKEN or not VK_PHOTO_GROUP_ID:
        logger.warning("VK_BOT_TOKEN или VK_PHOTO_GROUP_ID не настроены, пропускаем отправку фото")
        return None
    
    # Проверяем, есть ли уже attachment у этого фото (чтобы не отправлять повторно)
    if not skip_db_check:
        from api.products.database.database import async_session_maker
        from sqlalchemy import select
        from api.products.models.item_photo import ItemPhoto
        
        async with async_session_maker() as check_session:
            result = await check_session.execute(
                select(ItemPhoto).where(ItemPhoto.id == photo_id)
            )
            existing_photo = result.scalar_one_or_none()
            if existing_photo and existing_photo.vk_attachment:
                logger.info(f"Фото #{photo_id} уже имеет attachment ({existing_photo.vk_attachment}), пропускаем отправку")
                return existing_photo.vk_attachment
    
    logger.info(f"Отправляю фото #{photo_id} в VK группу {VK_PHOTO_GROUP_ID}, файл: {file_path}")
    
    try:
        # Проверяем существование файла
        photo_path = Path(file_path)
        if not photo_path.exists():
            # Пробуем разные варианты путей
            possible_paths = [
                Path(f"/app/{file_path}"),
                Path(file_path),
                Path(f"uploads/items/{photo_path.name}"),
                Path(f"/app/uploads/items/{photo_path.name}")
            ]
            for path in possible_paths:
                if path.exists():
                    photo_path = path
                    break
            else:
                logger.error(f"Файл не найден: {file_path}")
                return None
        
        # Загружаем фото и получаем attachment
        attachment = await upload_photo_to_vk_server(photo_path)
        
        if attachment:
            # Attachment получен, возвращаем его
            # Отправка в группу не требуется - attachment можно использовать напрямую в сообщениях
            logger.info(f"✅ Attachment получен: {attachment}")
            return attachment
        else:
            logger.error(f"❌ Не удалось получить attachment для фото #{photo_id}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при отправке фото #{photo_id} в VK: {e}", exc_info=True)
        return None
