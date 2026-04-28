"""
Утилита для загрузки курса валют из API ЦБ РФ
Адаптировано из utils/exchange_rate.py для finance-service
"""
import logging
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import httpx
import json
import re
import xml.etree.ElementTree as ET
from os import getenv

from api.finance.database.database import get_session, async_session_maker
from api.finance.models.exchange_rate import ExchangeRate
from api.finance.models.finance_settings import FinanceSettings

logger = logging.getLogger(__name__)

# Код юаня в API ЦБ
CNY_CODE = "CNY"


async def load_exchange_rate(session: Optional[AsyncSession] = None) -> bool:
    """Загрузка/обновление курса юаня к рублю от ЦБ РФ с наценкой"""
    try:
        logger.info("Начало загрузки курса валют CNY")
        # Получаем курс от ЦБ через прямой запрос к API
        base_rate = None
        
        # Используем прямой запрос к API ЦБ
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        logger.info(f"Используем User-Agent: {headers['User-Agent']}")
        
        # 1. Альтернативный JSON API
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                url = "https://www.cbr-xml-daily.ru/daily_json.js"
                logger.info(f"[1/7] Попытка получить курс с {url}")
                response = await client.get(url, timeout=15.0, headers=headers)
                logger.info(f"[1/7] Ответ от cbr-xml-daily.ru: статус {response.status_code}")
                if response.status_code == 200:
                    try:
                        text = response.text
                        logger.debug(f"[1/7] Получен ответ длиной {len(text)} символов, первые 500: {text[:500]}")
                        # Пробуем парсить как JSON
                        try:
                            data = json.loads(text)
                            logger.debug(f"[1/7] JSON распарсен, ключи: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                            if 'Valute' in data and isinstance(data['Valute'], dict) and CNY_CODE in data['Valute']:
                                cny_data = data['Valute'][CNY_CODE]
                                logger.debug(f"[1/7] Данные CNY: {cny_data}")
                                if 'Value' in cny_data:
                                    base_rate = Decimal(str(cny_data['Value']))
                                    logger.info(f"[1/7] ✓ Получен курс с cbr-xml-daily.ru (через JSON): {base_rate}")
                            else:
                                logger.warning(f"[1/7] CNY не найден в данных. Valute существует: {'Valute' in data}, ключи Valute: {list(data.get('Valute', {}).keys())[:10] if isinstance(data.get('Valute'), dict) else 'не dict'}")
                        except json.JSONDecodeError as je:
                            logger.warning(f"[1/7] Ошибка парсинга JSON: {je}, первые 500 символов: {text[:500]}")
                            # Пробуем найти значение через regex
                            value_match = re.search(r'"CNY"[^}]*"Value"\s*:\s*([\d.]+)', text)
                            if value_match:
                                base_rate = Decimal(value_match.group(1))
                                logger.info(f"[1/7] ✓ Получен курс с cbr-xml-daily.ru (через regex): {base_rate}")
                    except Exception as e:
                        logger.warning(f"[1/7] Ошибка при парсинге ответа от cbr-xml-daily.ru: {e}", exc_info=True)
                else:
                    logger.warning(f"[1/7] Неверный статус от cbr-xml-daily.ru: {response.status_code}, ответ: {response.text[:200]}")
        except httpx.TimeoutException:
            logger.warning(f"[1/7] Таймаут при запросе к cbr-xml-daily.ru")
        except httpx.ConnectError as e:
            logger.warning(f"[1/7] Ошибка подключения к cbr-xml-daily.ru: {e}")
        except Exception as e:
            logger.warning(f"[1/7] Исключение при запросе к cbr-xml-daily.ru: {type(e).__name__}: {e}", exc_info=True)
        
        # 2. Если не получилось, пробуем официальный XML API ЦБ
        if not base_rate:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    url = "https://www.cbr.ru/scripts/XML_daily.asp"
                    logger.info(f"[2/7] Попытка получить курс с {url}")
                    response = await client.get(url, timeout=15.0, headers=headers)
                    logger.info(f"[2/7] Ответ от cbr.ru: статус {response.status_code}")
                    if response.status_code == 200:
                        xml_text = response.text
                        logger.debug(f"[2/7] Получен XML ответ длиной {len(xml_text)} символов, первые 500: {xml_text[:500]}")
                        root = ET.fromstring(xml_text)
                        
                        # Ищем валюту CNY (код 156)
                        found_cny = False
                        valute_count = 0
                        for valute in root.findall('Valute'):
                            valute_count += 1
                            char_code = valute.find('CharCode')
                            if char_code is not None and char_code.text == CNY_CODE:
                                found_cny = True
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
                                    logger.info(f"[2/7] ✓ Получен курс с cbr.ru: {base_rate} (значение={value_str}, номинал={nominal})")
                                    break
                        if not found_cny:
                            logger.warning(f"[2/7] CNY не найден в XML ответе от cbr.ru (найдено {valute_count} валют)")
                    else:
                        logger.warning(f"[2/7] Неверный статус от cbr.ru: {response.status_code}, ответ: {response.text[:200]}")
            except httpx.TimeoutException:
                logger.warning(f"[2/7] Таймаут при запросе к cbr.ru")
            except httpx.ConnectError as e:
                logger.warning(f"[2/7] Ошибка подключения к cbr.ru: {e}")
            except ET.ParseError as e:
                logger.warning(f"[2/7] Ошибка парсинга XML от cbr.ru: {e}")
            except Exception as e:
                logger.warning(f"[2/7] Исключение при запросе к cbr.ru: {type(e).__name__}: {e}", exc_info=True)
        
        # 3. Если не получилось, пробуем exchangerate-api.com
        if not base_rate:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    url = "https://open.er-api.com/v6/latest/CNY"
                    logger.info(f"[3/7] Попытка получить курс с {url}")
                    response = await client.get(url, timeout=15.0, headers=headers)
                    logger.info(f"[3/7] Ответ от exchangerate-api.com: статус {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        logger.debug(f"[3/7] Получен ответ от exchangerate-api.com, ключи: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                        if 'rates' in data and isinstance(data['rates'], dict) and 'RUB' in data['rates']:
                            # API возвращает курс CNY к RUB (сколько рублей за 1 юань)
                            base_rate = Decimal(str(data['rates']['RUB']))
                            logger.info(f"[3/7] ✓ Получен курс с exchangerate-api.com: {base_rate}")
                        else:
                            logger.warning(f"[3/7] RUB не найден в ответе. rates существует: {'rates' in data}, ключи rates: {list(data.get('rates', {}).keys())[:10] if isinstance(data, dict) and 'rates' in data else 'нет rates'}")
                    else:
                        logger.warning(f"[3/7] Неверный статус от exchangerate-api.com: {response.status_code}, ответ: {response.text[:200]}")
            except httpx.TimeoutException:
                logger.warning(f"[3/7] Таймаут при запросе к exchangerate-api.com")
            except httpx.ConnectError as e:
                logger.warning(f"[3/7] Ошибка подключения к exchangerate-api.com: {e}")
            except Exception as e:
                logger.warning(f"[3/7] Исключение при запросе к exchangerate-api.com: {type(e).__name__}: {e}", exc_info=True)
        
        # 4. Если не получилось, пробуем currency-api через jsdelivr
        if not base_rate:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    url = "https://cdn.jsdelivr.net/gh/fawazahmed0/currency-api@1/latest/currencies/cny/rub.json"
                    logger.info(f"[4/7] Попытка получить курс с {url}")
                    response = await client.get(url, timeout=15.0, headers=headers)
                    logger.info(f"[4/7] Ответ от currency-api (jsdelivr): статус {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        logger.debug(f"[4/7] Получен ответ от currency-api, ключи: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                        if 'rub' in data:
                            # API возвращает курс CNY к RUB
                            base_rate = Decimal(str(data['rub']))
                            logger.info(f"[4/7] ✓ Получен курс с currency-api (jsdelivr): {base_rate}")
                        else:
                            logger.warning(f"[4/7] rub не найден в ответе. Доступные ключи: {list(data.keys())[:10] if isinstance(data, dict) else 'не dict'}")
                    else:
                        logger.warning(f"[4/7] Неверный статус от currency-api: {response.status_code}, ответ: {response.text[:200]}")
            except httpx.TimeoutException:
                logger.warning(f"[4/7] Таймаут при запросе к currency-api")
            except httpx.ConnectError as e:
                logger.warning(f"[4/7] Ошибка подключения к currency-api: {e}")
            except Exception as e:
                logger.warning(f"[4/7] Исключение при запросе к currency-api: {type(e).__name__}: {e}", exc_info=True)
        
        # 5. Если не получилось, пробуем exchangerate.host
        if not base_rate:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    url = "https://api.exchangerate.host/latest?base=CNY&symbols=RUB"
                    logger.info(f"[5/7] Попытка получить курс с {url}")
                    response = await client.get(url, timeout=15.0, headers=headers)
                    logger.info(f"[5/7] Ответ от exchangerate.host: статус {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        logger.debug(f"[5/7] Получен ответ от exchangerate.host: success={data.get('success') if isinstance(data, dict) else 'не dict'}")
                        if 'success' in data and data.get('success') and 'rates' in data and isinstance(data['rates'], dict) and 'RUB' in data['rates']:
                            base_rate = Decimal(str(data['rates']['RUB']))
                            logger.info(f"[5/7] ✓ Получен курс с exchangerate.host: {base_rate}")
                        else:
                            logger.warning(f"[5/7] Курс не найден. success={data.get('success') if isinstance(data, dict) else None}, rates keys: {list(data.get('rates', {}).keys())[:10] if isinstance(data, dict) and 'rates' in data else 'нет rates'}")
                    else:
                        logger.warning(f"[5/7] Неверный статус от exchangerate.host: {response.status_code}, ответ: {response.text[:200]}")
            except httpx.TimeoutException:
                logger.warning(f"[5/7] Таймаут при запросе к exchangerate.host")
            except httpx.ConnectError as e:
                logger.warning(f"[5/7] Ошибка подключения к exchangerate.host: {e}")
            except Exception as e:
                logger.warning(f"[5/7] Исключение при запросе к exchangerate.host: {type(e).__name__}: {e}", exc_info=True)
        
        # 6. Если не получилось, пробуем fixer.io (может требовать API key, но есть бесплатный tier)
        if not base_rate:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    url = "https://api.fixer.io/latest?base=CNY&symbols=RUB"
                    logger.info(f"[6/7] Попытка получить курс с {url}")
                    response = await client.get(url, timeout=15.0, headers=headers)
                    logger.info(f"[6/7] Ответ от fixer.io: статус {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        logger.debug(f"[6/7] Получен ответ от fixer.io, ключи: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                        if 'rates' in data and isinstance(data['rates'], dict) and 'RUB' in data['rates']:
                            base_rate = Decimal(str(data['rates']['RUB']))
                            logger.info(f"[6/7] ✓ Получен курс с fixer.io: {base_rate}")
                        else:
                            logger.warning(f"[6/7] RUB не найден. rates keys: {list(data.get('rates', {}).keys())[:10] if isinstance(data, dict) and 'rates' in data else 'нет rates'}")
                    else:
                        logger.warning(f"[6/7] Неверный статус от fixer.io: {response.status_code}, ответ: {response.text[:200]}")
            except httpx.TimeoutException:
                logger.warning(f"[6/7] Таймаут при запросе к fixer.io")
            except httpx.ConnectError as e:
                logger.warning(f"[6/7] Ошибка подключения к fixer.io: {e}")
            except Exception as e:
                logger.warning(f"[6/7] Исключение при запросе к fixer.io: {type(e).__name__}: {e}", exc_info=True)
        
        # 7. Если ничего не помогло, проверяем существующий курс в БД (если есть)
        used_existing_rate = False
        if not base_rate:
            logger.warning("[7/7] Не удалось получить курс ни из одного API источника (1-6), проверяем БД...")
            # Используем переданную сессию или создаем новую для проверки
            if session:
                check_session = session
                check_should_close = False
            else:
                check_session = async_session_maker()
                check_should_close = True
            
            try:
                logger.info("Выполняем запрос к БД для проверки существующего курса...")
                result = await check_session.execute(
                    select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
                )
                existing_rate = result.scalar_one_or_none()
                logger.info(f"Результат запроса к БД: found={existing_rate is not None}, rate={existing_rate.rate if existing_rate else None}")
                if existing_rate and existing_rate.rate:
                    logger.warning(f"Не удалось обновить курс из API, используем существующий из БД: {existing_rate.rate}")
                    base_rate = existing_rate.rate
                    used_existing_rate = True
                    # Если сессия была временной, закрываем её - будем создавать новую для сохранения
                    if check_should_close:
                        await check_session.close()
                        check_session = None
                else:
                    logger.warning("В БД нет сохраненного курса CNY")
            except Exception as e:
                logger.error(f"Ошибка при проверке существующего курса в БД: {e}", exc_info=True)
                if check_should_close and check_session:
                    try:
                        await check_session.close()
                    except:
                        pass
                    check_session = None
        
        if not base_rate:
            logger.error("Не удалось получить курс ни с одного источника и в БД нет сохраненного курса")
            return False
        
        if not base_rate or base_rate <= 0:
            logger.error(f"Получен некорректный курс: {base_rate}")
            return False
        
        # Используем переданную сессию или создаем новую
        if session:
            db_session = session
            should_close = False
        else:
            db_session = async_session_maker()
            should_close = True
        
        try:
            # Получаем настройку наценки на курс из FinanceSettings
            settings_result = await db_session.execute(select(FinanceSettings).limit(1))
            finance_settings = settings_result.scalar_one_or_none()
            
            # Используем настройку наценки или значение по умолчанию 10%
            margin_percent = Decimal("10.00")
            if finance_settings and finance_settings.exchange_rate_margin_percent:
                margin_percent = finance_settings.exchange_rate_margin_percent
            
            # Добавляем наценку на курс
            rate_with_margin = base_rate * (Decimal("1") + margin_percent / Decimal("100"))
            
            # Проверяем, есть ли уже запись о курсе
            result = await db_session.execute(
                select(ExchangeRate).where(ExchangeRate.currency_code == CNY_CODE)
            )
            exchange_rate = result.scalar_one_or_none()
            
            if exchange_rate:
                # Обновляем существующий курс
                exchange_rate.rate = base_rate
                exchange_rate.rate_with_margin = rate_with_margin
                exchange_rate.updated_at = datetime.now()
                if used_existing_rate:
                    logger.info(f"Курс {CNY_CODE} обновлен (использован существующий из БД): {base_rate} -> {rate_with_margin} (с наценкой {margin_percent}%)")
                else:
                    logger.info(f"Курс {CNY_CODE} загружен: {base_rate} -> {rate_with_margin} (с наценкой {margin_percent}%)")
            else:
                # Создаем новую запись
                exchange_rate = ExchangeRate(
                    currency_code=CNY_CODE,
                    rate=base_rate,
                    rate_with_margin=rate_with_margin
                )
                db_session.add(exchange_rate)
                logger.info(f"Курс {CNY_CODE} создан: {base_rate} -> {rate_with_margin} (с наценкой {margin_percent}%)")
            
            await db_session.commit()
            
            # Уведомляем products-service о необходимости пересчитать историю цен
            try:
                PRODUCTS_SERVICE_URL = getenv("PRODUCTS_SERVICE_URL", "http://products-service:8002")
                INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{PRODUCTS_SERVICE_URL}/internal/recalculate-price-history",
                        headers={"X-Internal-Token": INTERNAL_TOKEN},
                        timeout=60.0  # Может занять время для всех товаров
                    )
                    if response.status_code == 200:
                        result_data = response.json()
                        logger.info(f"История цен пересчитана после обновления курса: {result_data}")
                    else:
                        logger.warning(f"Не удалось пересчитать историю цен: {response.status_code}")
            except Exception as e:
                logger.error(f"Ошибка при уведомлении products-service о пересчете истории цен: {e}")
                # Не прерываем обновление курса, даже если не удалось уведомить products-service
            
            return True
            
        finally:
            if should_close:
                await db_session.close()
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке курса валют: {e}", exc_info=True)
        return False

