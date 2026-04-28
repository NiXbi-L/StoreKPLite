"""
Утилита для работы с курсом валют через API ЦБ РФ
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from database.database import async_session_maker
from database.models import ExchangeRate, Item, ItemPriceHistory

logger = logging.getLogger(__name__)

# Импортируем cbrapi с обработкой ошибок
try:
    import cbrapi
    CBRAPI_AVAILABLE = True
except ImportError:
    CBRAPI_AVAILABLE = False
    logger.warning("Библиотека cbrapi не установлена, будет использован альтернативный способ получения курса")

# Код юаня в API ЦБ
CNY_CODE = "CNY"


async def update_exchange_rate():
    """Обновление курса юаня к рублю от ЦБ РФ с наценкой 10%"""
    try:
        # Получаем курс от ЦБ
        base_rate = None
        
        # Пробуем использовать cbrapi через класс CbrApi
        if CBRAPI_AVAILABLE:
            try:
                from cbrapi import CbrApi
                api = CbrApi()
                # Получаем курс валюты
                rate_data = api.get_currency(CNY_CODE)
                if rate_data:
                    # rate_data может быть словарем или числом
                    if isinstance(rate_data, dict):
                        # Пробуем разные варианты ключей
                        if 'value' in rate_data:
                            base_rate = Decimal(str(rate_data['value']))
                        elif 'rate' in rate_data:
                            base_rate = Decimal(str(rate_data['rate']))
                        elif 'Value' in rate_data:
                            base_rate = Decimal(str(rate_data['Value']))
                    elif isinstance(rate_data, (int, float, str)):
                        base_rate = Decimal(str(rate_data))
            except Exception as e:
                logger.warning(f"Не удалось получить курс через cbrapi: {e}")
        
        # Если cbrapi не сработал, используем прямой запрос к API ЦБ
        if not base_rate:
            try:
                import aiohttp
                import json
                import re
                
                # Пробуем получить курс с разных источников
                # 1. Альтернативный JSON API
                try:
                    async with aiohttp.ClientSession() as session_http:
                        # Используем альтернативный источник с правильным JSON
                        url = "https://www.cbr-xml-daily.ru/daily_json.js"
                        async with session_http.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                try:
                                    # Читаем как текст, так как может быть JavaScript
                                    text = await response.text()
                                    
                                    # Пробуем извлечь JSON из JavaScript
                                    # Ищем паттерн вида: var data = {...} или просто {...}
                                    json_match = re.search(r'\{[^{}]*"Valute"[^{}]*\{[^{}]*"CNY"[^{}]*\{[^}]*"Value"[^}]*\}', text, re.DOTALL)
                                    if json_match:
                                        # Пробуем найти полный JSON объект
                                        start = text.find('{')
                                        if start >= 0:
                                            # Ищем закрывающую скобку на том же уровне
                                            bracket_count = 0
                                            end = start
                                            for i in range(start, len(text)):
                                                if text[i] == '{':
                                                    bracket_count += 1
                                                elif text[i] == '}':
                                                    bracket_count -= 1
                                                    if bracket_count == 0:
                                                        end = i + 1
                                                        break
                                            
                                            if end > start:
                                                json_str = text[start:end]
                                                try:
                                                    data = json.loads(json_str)
                                                    if 'Valute' in data and CNY_CODE in data['Valute']:
                                                        base_rate = Decimal(str(data['Valute'][CNY_CODE]['Value']))
                                                except json.JSONDecodeError:
                                                    # Пробуем найти значение напрямую через regex
                                                    value_match = re.search(r'"CNY"[^}]*"Value"\s*:\s*([\d.]+)', text)
                                                    if value_match:
                                                        base_rate = Decimal(value_match.group(1))
                                except Exception as e:
                                    logger.debug(f"Ошибка при парсинге JSON из JavaScript: {e}")
                except Exception as e:
                    logger.debug(f"Ошибка при запросе к cbr-xml-daily.ru: {e}")
                
                # 2. Если не получилось, пробуем официальный XML API ЦБ
                if not base_rate:
                    try:
                        from datetime import datetime
                        import xml.etree.ElementTree as ET
                        
                        async with aiohttp.ClientSession() as session_http:
                            # Официальный XML API ЦБ
                            url = "https://www.cbr.ru/scripts/XML_daily.asp"
                            async with session_http.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                                if response.status == 200:
                                    xml_text = await response.text()
                                    root = ET.fromstring(xml_text)
                                    
                                    # Ищем валюту CNY (код 156)
                                    for valute in root.findall('Valute'):
                                        char_code = valute.find('CharCode')
                                        if char_code is not None and char_code.text == CNY_CODE:
                                            value_elem = valute.find('Value')
                                            nominal_elem = valute.find('Nominal')
                                            if value_elem is not None:
                                                # Значение в XML - это за номинал (обычно 1 или 10)
                                                value_str = value_elem.text.replace(',', '.')
                                                nominal = 1
                                                if nominal_elem is not None:
                                                    nominal = int(nominal_elem.text)
                                                # Курс за 1 единицу валюты
                                                base_rate = Decimal(value_str) / Decimal(nominal)
                                                break
                    except Exception as e:
                        logger.debug(f"Ошибка при запросе к официальному API ЦБ: {e}")
                
                if not base_rate:
                    raise ValueError("Не удалось получить курс ни с одного источника")
            except Exception as e:
                logger.error(f"Ошибка при получении курса через API ЦБ: {e}")
                return False
        
        if not base_rate or base_rate <= 0:
            logger.error(f"Получен некорректный курс: {base_rate}")
            return False
        
        async with async_session_maker() as session:
            # Получаем настройку наценки на курс из FinanceSettings
            from database.models import FinanceSettings
            settings_result = await session.execute(select(FinanceSettings).limit(1))
            finance_settings = settings_result.scalar_one_or_none()
            
            # Используем настройку наценки или значение по умолчанию 10%
            margin_percent = Decimal("10.00")
            if finance_settings and finance_settings.exchange_rate_margin_percent:
                margin_percent = finance_settings.exchange_rate_margin_percent
            
            # Добавляем наценку на курс
            rate_with_margin = base_rate * (Decimal("1") + margin_percent / Decimal("100"))
            
            # Проверяем, есть ли уже запись о курсе
            result = await session.execute(
                select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
            )
            exchange_rate = result.scalar_one_or_none()
            
            if exchange_rate:
                # Обновляем существующий курс
                exchange_rate.rate = base_rate
                exchange_rate.rate_with_margin = rate_with_margin
                exchange_rate.updated_at = datetime.now()
            else:
                # Создаем новую запись
                exchange_rate = ExchangeRate(
                    currency_code=CNY_CODE,
                    rate=base_rate,
                    rate_with_margin=rate_with_margin
                )
                session.add(exchange_rate)
            
            await session.commit()
            logger.info(f"Курс {CNY_CODE} обновлен: {base_rate} -> {rate_with_margin} (с наценкой 10%)")
            
            # Обновляем историю цен товаров
            await update_item_price_history(session)
            
            return True
            
    except Exception as e:
        logger.error(f"Ошибка при обновлении курса валют: {e}", exc_info=True)
        return False


async def get_exchange_rate() -> Decimal:
    """Получить текущий курс юаня к рублю с наценкой 10%"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
        )
        exchange_rate = result.scalar_one_or_none()
        
        if exchange_rate:
            return exchange_rate.rate_with_margin
        else:
            # Если курса нет, пытаемся обновить
            await update_exchange_rate()
            # Повторно получаем
            result = await session.execute(
                select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
            )
            exchange_rate = result.scalar_one_or_none()
            if exchange_rate:
                return exchange_rate.rate_with_margin
            else:
                # Если все равно нет, возвращаем примерный курс (примерно 12.5 с наценкой)
                logger.warning("Курс не найден, используется значение по умолчанию")
                return Decimal("12.5")


async def calculate_item_price(item: Item, exchange_rate: Optional[Decimal] = None, session: Optional[AsyncSession] = None) -> Decimal:
    """
    Рассчитывает итоговую цену товара для клиента
    
    Формула: A * B + C + (A*B) * (D/100)
    где:
    A = стоимость в юанях
    B = курс юаня к рублю от ЦБ + 10%
    C = стоимость доставки (ориентировочный вес * стоимость доставки за 1 кг)
    D = сервисный сбор в процентах
    
    Args:
        item: Товар
        exchange_rate: Курс валюты (если None, будет получен из БД)
        session: Сессия БД (опционально, для оптимизации запросов)
    """
    if exchange_rate is None:
        exchange_rate = await get_exchange_rate()
    
    # A = цена в юанях
    price_cny = item.price
    
    # B = курс с наценкой
    rate = exchange_rate
    
    # A * B
    price_rub_base = price_cny * rate
    
    # C = стоимость доставки (получаем глобальную настройку)
    delivery_cost = Decimal(0)
    if item.estimated_weight_kg:
        # Получаем глобальную стоимость доставки за кг из FinanceSettings
        from database.models import FinanceSettings
        if session:
            # Используем переданную сессию
            result = await session.execute(select(FinanceSettings).limit(1))
            finance_settings = result.scalar_one_or_none()
        else:
            # Создаем новую сессию
            async with async_session_maker() as new_session:
                result = await new_session.execute(select(FinanceSettings).limit(1))
                finance_settings = result.scalar_one_or_none()
        
        if finance_settings and finance_settings.delivery_cost_per_kg:
            delivery_cost = item.estimated_weight_kg * finance_settings.delivery_cost_per_kg
    
    # D = сервисный сбор в процентах
    service_fee_percent = item.service_fee_percent or Decimal(0)
    
    # (A*B) * (D/100)
    service_fee = price_rub_base * (service_fee_percent / Decimal("100"))
    
    # Итоговая цена
    total_price = price_rub_base + delivery_cost + service_fee
    
    return total_price


async def update_item_price_history_for_item(session, item: Item):
    """Обновляет историю минимальных и максимальных цен конкретного товара за неделю"""
    try:
        # Получаем текущий курс
        result = await session.execute(
            select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
        )
        exchange_rate_obj = result.scalar_one_or_none()
        
        if not exchange_rate_obj:
            logger.warning("Курс валют не найден, пропускаем обновление истории цен")
            return
        
        exchange_rate = exchange_rate_obj.rate_with_margin
        
        # Получаем начало текущей недели (понедельник)
        today = datetime.now().date()
        days_since_monday = today.weekday()
        week_start = datetime.combine(today - timedelta(days=days_since_monday), datetime.min.time())
        
        # Рассчитываем текущую цену (передаем сессию для оптимизации)
        current_price = await calculate_item_price(item, exchange_rate, session)
        
        # Проверяем, есть ли запись за эту неделю
        history_result = await session.execute(
            select(ItemPriceHistory).where(
                ItemPriceHistory.item_id == item.id,
                ItemPriceHistory.week_start == week_start
            )
        )
        history = history_result.scalar_one_or_none()
        
        if history:
            # Обновляем мин/макс цены
            if current_price < history.min_price:
                history.min_price = current_price
            if current_price > history.max_price:
                history.max_price = current_price
        else:
            # Создаем новую запись
            history = ItemPriceHistory(
                item_id=item.id,
                week_start=week_start,
                min_price=current_price,
                max_price=current_price
            )
            session.add(history)
        
        await session.commit()
        logger.debug(f"История цен товара {item.id} обновлена: мин={current_price}, макс={current_price}")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении истории цен товара {item.id}: {e}", exc_info=True)
        await session.rollback()


async def update_item_price_history(session):
    """Обновляет историю минимальных и максимальных цен всех товаров за неделю"""
    try:
        # Получаем текущий курс
        result = await session.execute(
            select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
        )
        exchange_rate_obj = result.scalar_one_or_none()
        
        if not exchange_rate_obj:
            logger.warning("Курс валют не найден, пропускаем обновление истории цен")
            return
        
        exchange_rate = exchange_rate_obj.rate_with_margin
        
        # Получаем начало текущей недели (понедельник)
        today = datetime.now().date()
        days_since_monday = today.weekday()
        week_start = datetime.combine(today - timedelta(days=days_since_monday), datetime.min.time())
        
        # Получаем все товары
        items_result = await session.execute(select(Item))
        items = items_result.scalars().all()
        
        for item in items:
            # Рассчитываем текущую цену (передаем сессию для оптимизации)
            current_price = await calculate_item_price(item, exchange_rate, session)
            
            # Проверяем, есть ли запись за эту неделю
            history_result = await session.execute(
                select(ItemPriceHistory).where(
                    ItemPriceHistory.item_id == item.id,
                    ItemPriceHistory.week_start == week_start
                )
            )
            history = history_result.scalar_one_or_none()
            
            if history:
                # Обновляем мин/макс цены
                if current_price < history.min_price:
                    history.min_price = current_price
                if current_price > history.max_price:
                    history.max_price = current_price
            else:
                # Создаем новую запись
                history = ItemPriceHistory(
                    item_id=item.id,
                    week_start=week_start,
                    min_price=current_price,
                    max_price=current_price
                )
                session.add(history)
        
        await session.commit()
        logger.info("История цен товаров обновлена")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении истории цен: {e}", exc_info=True)
        await session.rollback()

