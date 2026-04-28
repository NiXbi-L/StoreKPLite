"""
Утилиты для получения метаданных о структуре БД
"""
from sqlalchemy import inspect, Column, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Dict, List, Any, Optional
import json
from decimal import Decimal
from datetime import datetime, date


def serialize_value(value: Any) -> Any:
    """Сериализация значения для JSON"""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        return json.loads(json.dumps(value, default=str)) if isinstance(value, (dict, list)) else value
    return value


def get_column_type_str(column: Column) -> str:
    """Получить строковое представление типа колонки"""
    col_type = str(column.type)
    # Упрощаем некоторые типы для лучшего отображения
    if 'VARCHAR' in col_type or 'TEXT' in col_type:
        return 'string'
    elif 'INTEGER' in col_type:
        return 'integer'
    elif 'BIGINT' in col_type:
        return 'bigint'
    elif 'NUMERIC' in col_type or 'DECIMAL' in col_type:
        return 'numeric'
    elif 'BOOLEAN' in col_type:
        return 'boolean'
    elif 'JSON' in col_type:
        return 'json'
    elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
        return 'datetime'
    elif 'DATE' in col_type:
        return 'date'
    return col_type.lower()


async def get_table_metadata(session: AsyncSession, model_class) -> Dict[str, Any]:
    """Получить метаданные таблицы из модели SQLAlchemy"""
    mapper = inspect(model_class)
    table_name = mapper.tables[0].name if mapper.tables else mapper.class_.__tablename__
    
    columns_info = []
    primary_keys = []
    
    for column in mapper.columns:
        col_info = {
            "name": column.name,
            "type": get_column_type_str(column),
            "nullable": column.nullable,
            "primary_key": column.primary_key,
            "default": str(column.default.arg) if column.default and hasattr(column.default, 'arg') else None,
        }
        
        if column.primary_key:
            primary_keys.append(column.name)
        
        # Определяем внешние ключи
        if hasattr(column, 'foreign_keys') and column.foreign_keys:
            fk = list(column.foreign_keys)[0]
            col_info["foreign_key"] = {
                "table": fk.column.table.name,
                "column": fk.column.name
            }
        
        columns_info.append(col_info)
    
    # Получаем количество записей
    try:
        result = await session.execute(select(model_class))
        count = len(result.scalars().all())
    except Exception:
        count = 0
    
    return {
        "table_name": table_name,
        "columns": columns_info,
        "primary_keys": primary_keys,
        "count": count
    }


async def get_all_tables_metadata(session: AsyncSession, models: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Получить метаданные всех таблиц"""
    tables_metadata = []
    
    for table_key, model_info in models.items():
        if isinstance(model_info, dict) and "model" in model_info:
            model_class = model_info["model"]
            try:
                metadata = await get_table_metadata(session, model_class)
                metadata["display_name"] = model_info.get("name", table_key)
                metadata["description"] = model_info.get("description", "")
                tables_metadata.append(metadata)
            except Exception as e:
                # Пропускаем таблицы, для которых не удалось получить метаданные
                continue
    
    return tables_metadata


async def get_table_data(
    session: AsyncSession,
    model_class,
    skip: int = 0,
    limit: int = 100,
    primary_key_field: Optional[str] = None
) -> Dict[str, Any]:
    """Получить данные из таблицы с пагинацией"""
    mapper = inspect(model_class)
    
    # Определяем primary key
    if not primary_key_field:
        for column in mapper.columns:
            if column.primary_key:
                primary_key_field = column.name
                break
    
    # Получаем общее количество
    count_result = await session.execute(select(func.count()).select_from(model_class))
    total_count = count_result.scalar() or 0
    
    # Получаем данные с пагинацией
    result = await session.execute(
        select(model_class).offset(skip).limit(limit)
    )
    records = result.scalars().all()
    
    # Преобразуем в словари
    records_list = []
    for record in records:
        record_dict = {}
        for column in mapper.columns:
            value = getattr(record, column.name, None)
            record_dict[column.name] = serialize_value(value)
        records_list.append(record_dict)
    
    return {
        "records": records_list,
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "primary_key": primary_key_field
    }


async def get_table_record(
    session: AsyncSession,
    model_class,
    primary_key_value: Any,
    primary_key_field: str
) -> Optional[Dict[str, Any]]:
    """Получить одну запись по primary key"""
    mapper = inspect(model_class)
    primary_key_column = getattr(model_class, primary_key_field, None)
    
    if not primary_key_column:
        return None
    
    result = await session.execute(
        select(model_class).where(primary_key_column == primary_key_value)
    )
    record = result.scalar_one_or_none()
    
    if not record:
        return None
    
    record_dict = {}
    for column in mapper.columns:
        value = getattr(record, column.name, None)
        record_dict[column.name] = serialize_value(value)
    
    return record_dict


async def create_table_record(
    session: AsyncSession,
    model_class,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """Создать новую запись в таблице"""
    # Убираем primary key из данных, если он autoincrement или равен None/пустой строке
    mapper = inspect(model_class)
    cleaned_data = {}
    for key, value in data.items():
        # Пропускаем поля, которые не существуют в модели
        if key not in [col.name for col in mapper.columns]:
            continue
        # Пропускаем primary key если он autoincrement или пустой
        column = next((col for col in mapper.columns if col.name == key), None)
        if column and column.primary_key:
            # Проверяем autoincrement через SQLAlchemy
            if hasattr(column, 'autoincrement') and column.autoincrement in ('auto', True):
                continue
            # Также пропускаем если значение None или пустая строка
            if value is None or value == '':
                continue
        cleaned_data[key] = value
    
    new_record = model_class(**cleaned_data)
    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)
    
    record_dict = {}
    for column in mapper.columns:
        value = getattr(new_record, column.name, None)
        record_dict[column.name] = serialize_value(value)
    
    return record_dict


async def update_table_record(
    session: AsyncSession,
    model_class,
    primary_key_value: Any,
    primary_key_field: str,
    data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Обновить запись в таблице"""
    mapper = inspect(model_class)
    primary_key_column = getattr(model_class, primary_key_field, None)
    
    if not primary_key_column:
        return None
    
    result = await session.execute(
        select(model_class).where(primary_key_column == primary_key_value)
    )
    record = result.scalar_one_or_none()
    
    if not record:
        return None
    
    # Обновляем только те поля, которые есть в модели и не являются primary key
    for column in mapper.columns:
        if column.name in data and not column.primary_key:
            setattr(record, column.name, data[column.name])
    
    await session.commit()
    await session.refresh(record)
    
    record_dict = {}
    for column in mapper.columns:
        value = getattr(record, column.name, None)
        record_dict[column.name] = serialize_value(value)
    
    return record_dict


async def delete_table_record(
    session: AsyncSession,
    model_class,
    primary_key_value: Any,
    primary_key_field: str
) -> bool:
    """Удалить запись из таблицы"""
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text
    
    mapper = inspect(model_class)
    primary_key_column = getattr(model_class, primary_key_field, None)
    
    if not primary_key_column:
        return False
    
    result = await session.execute(
        select(model_class).where(primary_key_column == primary_key_value)
    )
    record = result.scalar_one_or_none()
    
    if not record:
        return False
    
    try:
        await session.delete(record)
        await session.commit()
        return True
    except IntegrityError as e:
        await session.rollback()
        # Проверяем, это ли ошибка foreign key constraint
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if 'foreign key' in error_msg.lower() or 'violates foreign key constraint' in error_msg.lower():
            # Пытаемся получить более детальную информацию об ошибке
            raise ValueError(
                f"Невозможно удалить запись: она используется в других таблицах. "
                f"Удалите сначала связанные записи."
            )
        # Для других IntegrityError пробрасываем как есть
        raise
    except Exception as e:
        await session.rollback()
        raise

