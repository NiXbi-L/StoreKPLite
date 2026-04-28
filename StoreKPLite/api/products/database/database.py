"""
Настройка базы данных для сервиса товаров
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from os import getenv

DATABASE_URL = getenv(
    "PRODUCTS_DATABASE_URL",
    getenv("DATABASE_URL", "postgresql+asyncpg://timoshka_user:timoshka_password@postgres:5432/timoshka_products")
)

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Есть ли расширение pg_trgm (similarity/word_similarity). Если нет — поиск только по ILIKE.
PG_TRGM_AVAILABLE = False


from typing import AsyncGenerator

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Инициализация базы данных"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Важно: импортируем все модели ДО вызова Base.metadata.create_all
    from api.products.models import (  # noqa: F401
        Item,
        ItemPhoto,
        ItemReview,
        ItemReviewPhoto,
        Like,
        Cart,
        Order,
        OrderDelivery,
        DeliveryStatus,
        ItemPriceHistory,
        ItemGroup,
        ItemType,
        Promocode,
        PromocodeItem,
        PromoRedemption,
        SystemPhotoPromoItem,
        SystemPhotoPromoSettings,
        ItemStyleProfile,
        ItemCompatibilityEdge,
    )
    
    # Сначала создаем все таблицы через SQLAlchemy
    logger.info("Создаем все таблицы через SQLAlchemy...")
    async with engine.begin() as conn:
        def create_tables(sync_conn):
            Base.metadata.create_all(bind=sync_conn)
        await conn.run_sync(create_tables)
    logger.info("Таблицы созданы через SQLAlchemy")
    
    # КРИТИЧНО: Сначала выполняем миграцию для критических колонок (is_from_stock, parent_order_id) 
    # в отдельной транзакции, чтобы они гарантированно были добавлены
    logger.info("Выполняем критическую миграцию для orders (is_from_stock, parent_order_id)...")
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            
            # Проверяем и добавляем is_from_stock
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'orders' AND column_name = 'is_from_stock')"
            ))
            is_from_stock_exists = result.scalar()
            
            if not is_from_stock_exists:
                logger.info("Добавляем колонку is_from_stock в таблицу orders...")
                await conn.execute(text("ALTER TABLE orders ADD COLUMN is_from_stock BOOLEAN NOT NULL DEFAULT FALSE"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_is_from_stock ON orders(is_from_stock)"))
                logger.info("✅ Колонка is_from_stock добавлена и закоммичена")
            else:
                logger.info("✅ Колонка is_from_stock уже существует")
            
            # Проверяем и добавляем parent_order_id
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'orders' AND column_name = 'parent_order_id')"
            ))
            parent_order_id_exists = result.scalar()
            
            if not parent_order_id_exists:
                logger.info("Добавляем колонку parent_order_id в таблицу orders...")
                await conn.execute(text("ALTER TABLE orders ADD COLUMN parent_order_id INTEGER"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_parent_order_id ON orders(parent_order_id)"))
                logger.info("✅ Колонка parent_order_id добавлена и закоммичена")
            else:
                logger.info("✅ Колонка parent_order_id уже существует")
        
        logger.info("✅ Критическая миграция для orders выполнена успешно")
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при добавлении колонок в orders: {e}", exc_info=True)
        raise
    
    # Затем выполняем остальные миграции для изменения существующих таблиц
    logger.info("Выполняем остальные миграции для изменения существующих таблиц...")
    try:
        async with engine.begin() as conn:
            await run_migrations(conn)
        logger.info("✅ Остальные миграции выполнены успешно")
    except Exception as e:
        logger.error(f"❌ ОШИБКА при выполнении остальных миграций: {e}", exc_info=True)
        # Не прерываем запуск, если остальные миграции не выполнились (критические уже выполнены)
        logger.warning("⚠️ Продолжаем работу, несмотря на ошибки в остальных миграциях")

    # Проверяем, установлено ли расширение pg_trgm (нужны права суперпользователя для CREATE EXTENSION)
    global PG_TRGM_AVAILABLE
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')"))
            row = result.fetchone()
            PG_TRGM_AVAILABLE = bool(row and row[0])
        logger.info(f"pg_trgm для нечёткого поиска: {'доступен' if PG_TRGM_AVAILABLE else 'не установлен (поиск только по ILIKE)'}")
    except Exception as e:
        logger.warning("Проверка pg_trgm не удалась: %s", e)
        PG_TRGM_AVAILABLE = False

    try:
        from api.products.utils.promo_apply import ensure_system_photo_promo_seed

        async with async_session_maker() as seed_session:
            await ensure_system_photo_promo_seed(seed_session)
    except Exception as e:
        logger.warning("ensure_system_photo_promo_seed: %s", e)


async def run_migrations(conn):
    """Выполнить SQL миграции для существующих таблиц"""
    import logging
    from sqlalchemy import text
    logger = logging.getLogger(__name__)
    
    try:
        # Расширение pg_trgm для нечёткого поиска (триграммы). Если нет прав — установите вручную: psql -U postgres -d timoshka_products -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        logger.info("pg_trgm extension ensured")
        # GIN-индекс по name для быстрого триграммного поиска (similarity, word_similarity)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'idx_items_name_gin_trgm')"
        ))
        if not result.scalar():
            logger.info("Создаём GIN-индекс по items.name для триграммного поиска...")
            await conn.execute(text(
                "CREATE INDEX idx_items_name_gin_trgm ON items USING gin (name gin_trgm_ops)"
            ))
            logger.info("GIN-индекс idx_items_name_gin_trgm создан")
        # Расширение fuzzystrmatch для Левенштейна (короткая строка к длинной)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch"))
        logger.info("fuzzystrmatch extension ensured")

        # Здесь выполняем миграции для изменения таблиц
        
        # Миграция: добавление таблицы групп товаров и поля group_id
        # Проверяем, существует ли таблица item_groups
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_groups')"
        ))
        groups_table_exists = result.scalar()
        
        if not groups_table_exists:
            logger.info("Создаем таблицу item_groups...")
            await conn.execute(text(
                "CREATE TABLE item_groups ("
                "id SERIAL PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
                ")"
            ))
            logger.info("Таблица item_groups создана")
        
        # Проверяем, существует ли колонка group_id в items
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'group_id')"
        ))
        group_id_exists = result.scalar()
        
        if not group_id_exists:
            logger.info("Добавляем колонку group_id в таблицу items...")
            await conn.execute(text("ALTER TABLE items ADD COLUMN group_id INTEGER"))
            logger.info("Колонка group_id добавлена")
            
            # Проверяем, существует ли внешний ключ
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.table_constraints "
                "WHERE constraint_name = 'items_group_id_fkey')"
            ))
            fk_exists = result.scalar()
            
            if not fk_exists:
                # Создаем внешний ключ
                await conn.execute(text(
                    "ALTER TABLE items "
                    "ADD CONSTRAINT items_group_id_fkey "
                    "FOREIGN KEY (group_id) REFERENCES item_groups(id) ON DELETE SET NULL"
                ))
                logger.info("Внешний ключ для group_id создан")
            
            # Создаем индекс (IF NOT EXISTS работает через проверку)
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'idx_items_group_id')"
            ))
            index_exists = result.scalar()
            
            if not index_exists:
                await conn.execute(text("CREATE INDEX idx_items_group_id ON items(group_id)"))
                logger.info("Индекс для group_id создан")
        
        # Миграция: добавление поля require_payment в таблицу delivery_statuses
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'delivery_statuses' AND column_name = 'require_payment')"
        ))
        require_payment_exists = result.scalar()
        
        if not require_payment_exists:
            logger.info("Добавляем колонку require_payment в таблицу delivery_statuses...")
            await conn.execute(text(
                "ALTER TABLE delivery_statuses "
                "ADD COLUMN require_payment BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            await conn.execute(text(
                "COMMENT ON COLUMN delivery_statuses.require_payment IS "
                "'Требовать оплату остатка при установке этого статуса'"
            ))
            logger.info("Колонка require_payment добавлена")
        
        # Миграция: изменение типа колонки size с VARCHAR на JSONB
        result = await conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'size'"
        ))
        size_column = result.scalar_one_or_none()
        
        if size_column and size_column == 'character varying':
            logger.info("Изменяем тип колонки size с VARCHAR на JSONB...")
            # Сначала устанавливаем NULL для всех существующих записей
            await conn.execute(text("UPDATE items SET size = NULL WHERE size IS NOT NULL"))
            logger.info("Все существующие значения size установлены в NULL")
            
            # Изменяем тип колонки на JSONB
            await conn.execute(text("ALTER TABLE items ALTER COLUMN size TYPE JSONB USING NULL"))
            logger.info("Тип колонки size изменен на JSONB")
        
        # Миграция: добавление поля tags (теги для поиска)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'tags')"
        ))
        tags_exists = result.scalar()
        if not tags_exists:
            logger.info("Добавляем колонку tags в таблицу items...")
            await conn.execute(text("ALTER TABLE items ADD COLUMN tags JSONB"))
            logger.info("Колонка tags добавлена")

        # Миграция: добавление опционального названия товара на китайском
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'chinese_name')"
        ))
        chinese_name_exists = result.scalar()
        if not chinese_name_exists:
            logger.info("Добавляем колонку chinese_name в таблицу items...")
            await conn.execute(text("ALTER TABLE items ADD COLUMN chinese_name VARCHAR(255)"))
            logger.info("Колонка chinese_name добавлена")
        
        # Миграция: добавление поля size в таблицу cart и обновление уникального индекса
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'cart' AND column_name = 'size')"
        ))
        cart_size_exists = result.scalar()
        
        if not cart_size_exists:
            logger.info("Добавляем колонку size в таблицу cart...")
            await conn.execute(text("ALTER TABLE cart ADD COLUMN size VARCHAR(50)"))
            logger.info("Колонка size добавлена в cart")
            
            # Удаляем старый уникальный индекс, если он существует
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_constraint WHERE conname = 'uq_cart_user_item')"
            ))
            old_index_exists = result.scalar()
            
            if old_index_exists:
                logger.info("Удаляем старый уникальный индекс uq_cart_user_item...")
                await conn.execute(text("ALTER TABLE cart DROP CONSTRAINT uq_cart_user_item"))
                logger.info("Старый индекс удален")
            
            # Создаем новый уникальный индекс с учетом размера
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_constraint WHERE conname = 'uq_cart_user_item_size')"
            ))
            new_index_exists = result.scalar()
            
            if not new_index_exists:
                logger.info("Создаем новый уникальный индекс uq_cart_user_item_size...")
                await conn.execute(text(
                    "ALTER TABLE cart "
                    "ADD CONSTRAINT uq_cart_user_item_size "
                    "UNIQUE (user_id, item_id, size)"
                ))
                logger.info("Новый индекс создан")
        
        # Миграция: item_price_history — avg_price и sample_count (средняя за 4h/день)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'item_price_history' AND column_name = 'avg_price')"
        ))
        avg_price_exists = result.scalar()
        if not avg_price_exists:
            logger.info("Добавляем колонки avg_price и sample_count в item_price_history...")
            await conn.execute(text(
                "ALTER TABLE item_price_history "
                "ADD COLUMN avg_price NUMERIC(10,2), "
                "ADD COLUMN sample_count INTEGER NOT NULL DEFAULT 1"
            ))
            await conn.execute(text(
                "UPDATE item_price_history SET avg_price = (min_price + max_price) / 2, sample_count = 1 WHERE avg_price IS NULL"
            ))
            logger.info("Колонки avg_price и sample_count добавлены")
        
        # Таблицы delivery_methods и user_delivery_data переехали в сервис доставки (delivery-service),
        # поэтому их миграции здесь больше не нужны.
        # Миграция: добавление полей доставки в таблицу orders
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'orders' AND column_name = 'delivery_method')"
        ))
        delivery_method_exists = result.scalar()
        
        if not delivery_method_exists:
            logger.info("Добавляем поля доставки в таблицу orders...")
            await conn.execute(text("ALTER TABLE orders ADD COLUMN delivery_method VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN delivery_address TEXT"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN phone_number VARCHAR(20)"))
            logger.info("Поля доставки добавлены в orders")
        
        # Миграция: добавление таблицы item_types и поля item_type_id
        # Проверяем, существует ли таблица item_types
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_types')"
        ))
        item_types_table_exists = result.scalar()
        
        if not item_types_table_exists:
            logger.info("Создаем таблицу item_types...")
            await conn.execute(text(
                "CREATE TABLE item_types ("
                "id SERIAL PRIMARY KEY, "
                "name VARCHAR(50) NOT NULL UNIQUE, "
                "created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            logger.info("Таблица item_types создана")
            
            # Вставляем существующие типы вещей
            logger.info("Вставляем существующие типы вещей...")
            await conn.execute(text(
                "INSERT INTO item_types (name) VALUES "
                "('Летняя обувь'), ('Худи'), ('Ветровки'), ('Штаны'), "
                "('Футболки'), ('Рубашки'), ('шорты'), ('Зимняя обувь'), "
                "('Куртки'), ('Аксессуары'), ('Головные уборы'), ('Сумки/рюкзаки') "
                "ON CONFLICT (name) DO NOTHING"
            ))
            logger.info("Типы вещей вставлены")
        
        # Проверяем, существует ли колонка item_type_id в items
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'item_type_id')"
        ))
        item_type_id_exists = result.scalar()
        
        if not item_type_id_exists:
            logger.info("Добавляем колонку item_type_id в таблицу items...")
            await conn.execute(text("ALTER TABLE items ADD COLUMN item_type_id INTEGER"))
            logger.info("Колонка item_type_id добавлена")
            
            # Заполняем item_type_id на основе существующих значений item_type
            logger.info("Заполняем item_type_id на основе существующих значений item_type...")
            await conn.execute(text(
                "UPDATE items "
                "SET item_type_id = (SELECT id FROM item_types WHERE item_types.name = items.item_type) "
                "WHERE item_type_id IS NULL"
            ))
            logger.info("item_type_id заполнен")
            
            # Делаем item_type_id NOT NULL (только если все записи заполнены)
            result = await conn.execute(text("SELECT COUNT(*) FROM items WHERE item_type_id IS NULL"))
            null_count = result.scalar()
            
            if null_count == 0:
                logger.info("Устанавливаем NOT NULL для item_type_id...")
                await conn.execute(text("ALTER TABLE items ALTER COLUMN item_type_id SET NOT NULL"))
                logger.info("NOT NULL установлен для item_type_id")
            else:
                logger.warning(f"Найдено {null_count} товаров без типа. NOT NULL не установлен.")
            
            # Проверяем, существует ли внешний ключ
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.table_constraints "
                "WHERE constraint_name = 'fk_items_item_type')"
            ))
            fk_exists = result.scalar()
            
            if not fk_exists:
                logger.info("Создаем внешний ключ для item_type_id...")
                await conn.execute(text(
                    "ALTER TABLE items "
                    "ADD CONSTRAINT fk_items_item_type "
                    "FOREIGN KEY (item_type_id) REFERENCES item_types(id) ON DELETE RESTRICT"
                ))
                logger.info("Внешний ключ для item_type_id создан")
            
            # Создаем индекс
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'idx_items_item_type_id')"
            ))
            index_exists = result.scalar()
            
            if not index_exists:
                await conn.execute(text("CREATE INDEX idx_items_item_type_id ON items(item_type_id)"))
                logger.info("Индекс для item_type_id создан")
        
        # Проверяем, существует ли еще старое поле item_type
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'item_type')"
        ))
        old_item_type_exists = result.scalar()
        
        if old_item_type_exists:
            # Проверяем, что все записи имеют item_type_id
            result = await conn.execute(text("SELECT COUNT(*) FROM items WHERE item_type_id IS NULL"))
            null_count = result.scalar()
            
            if null_count == 0:
                logger.info("Все товары имеют item_type_id, удаляем старое поле item_type...")
                # Сначала делаем поле nullable (если оно NOT NULL)
                try:
                    await conn.execute(text("ALTER TABLE items ALTER COLUMN item_type DROP NOT NULL"))
                except Exception:
                    # Игнорируем ошибку, если поле уже nullable
                    pass
                
                # Удаляем старое поле
                await conn.execute(text("ALTER TABLE items DROP COLUMN IF EXISTS item_type"))
                logger.info("Старое поле item_type удалено")
            else:
                logger.warning(f"Не удалось удалить старое поле item_type: найдено {null_count} товаров без item_type_id")
        
        # Миграция: items_count в item_types (для фильтра без сканирования БД)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'item_types' AND column_name = 'items_count')"
        ))
        items_count_exists = result.scalar()
        if not items_count_exists:
            logger.info("Добавляем колонку items_count в item_types...")
            await conn.execute(text(
                "ALTER TABLE item_types ADD COLUMN items_count INTEGER NOT NULL DEFAULT 0"
            ))
            await conn.execute(text(
                "UPDATE item_types t SET items_count = (SELECT COUNT(*) FROM items i WHERE i.item_type_id = t.id)"
            ))
            logger.info("Колонка items_count добавлена и заполнена")
        
        # Миграция: добавление поля sort_order в таблицу item_photos
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'item_photos' AND column_name = 'sort_order')"
        ))
        sort_order_exists = result.scalar()
        
        if not sort_order_exists:
            logger.info("Добавляем колонку sort_order в таблицу item_photos...")
            await conn.execute(text("ALTER TABLE item_photos ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
            logger.info("Колонка sort_order добавлена")
            
            # Устанавливаем sort_order для существующих фотографий на основе их id
            logger.info("Устанавливаем sort_order для существующих фотографий...")
            await conn.execute(text(
                "UPDATE item_photos SET sort_order = id - (SELECT MIN(id) FROM item_photos WHERE item_id = item_photos.item_id)"
            ))
            logger.info("sort_order установлен для существующих фотографий")
            
            # Создаем индекс
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'idx_item_photos_sort_order')"
            ))
            index_exists = result.scalar()
            
            if not index_exists:
                await conn.execute(text("CREATE INDEX idx_item_photos_sort_order ON item_photos(item_id, sort_order)"))
                logger.info("Индекс для sort_order создан")
        
        # Миграция: возврат fixed_price в items и таблицы item_stock, item_reservations (модуль Склад)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'fixed_price')"
        ))
        if not result.scalar():
            logger.info("Добавляем колонку fixed_price в items...")
            await conn.execute(text(
                "ALTER TABLE items ADD COLUMN fixed_price NUMERIC(10,2) NULL"
            ))
            logger.info("✅ Колонка fixed_price добавлена в items")
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_stock')"
        ))
        if not result.scalar():
            logger.info("Создаём таблицу item_stock...")
            await conn.execute(text("""
                CREATE TABLE item_stock (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    size VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                    UNIQUE (item_id, size)
                )
            """))
            await conn.execute(text("CREATE INDEX idx_item_stock_item_id ON item_stock(item_id)"))
            logger.info("✅ Таблица item_stock создана")
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_reservations')"
        ))
        if not result.scalar():
            logger.info("Создаём таблицу item_reservations...")
            await conn.execute(text("""
                CREATE TABLE item_reservations (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    size VARCHAR(50) NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    status VARCHAR(20) NOT NULL DEFAULT 'active'
                )
            """))
            await conn.execute(text("CREATE INDEX idx_item_reservations_item_id ON item_reservations(item_id)"))
            await conn.execute(text("CREATE INDEX idx_item_reservations_user_id ON item_reservations(user_id)"))
            await conn.execute(text("CREATE INDEX idx_item_reservations_status ON item_reservations(status)"))
            logger.info("✅ Таблица item_reservations создана")
        # Миграция: order_id в item_reservations (привязка резерва к заказу)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'item_reservations' AND column_name = 'order_id')"
        ))
        if not result.scalar():
            logger.info("Добавляем колонку order_id в item_reservations...")
            await conn.execute(text(
                "ALTER TABLE item_reservations ADD COLUMN order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL"
            ))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_item_reservations_order_id ON item_reservations(order_id)"))
            logger.info("✅ Колонка order_id в item_reservations добавлена")
        
        # Миграция: признак «легит/реплика» для товаров
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name = 'is_legit')"
        ))
        is_legit_exists = result.scalar()

        if not is_legit_exists:
            logger.info("Добавляем колонку is_legit в таблицу items...")
            await conn.execute(text("ALTER TABLE items ADD COLUMN is_legit BOOLEAN"))
            logger.info("Колонка is_legit добавлена")

            # По умолчанию считаем все вещи легитными, кроме кроссовок
            # (item_types.name = 'Кроссовки' или 'Кроссовки/кеды' — на всякий случай учитываем оба варианта)
            logger.info("Заполняем is_legit: все, кроме кроссовок, отмечаем как оригинал...")
            await conn.execute(text(
                "UPDATE items "
                "SET is_legit = TRUE "
                "WHERE item_type_id IN ("
                "  SELECT id FROM item_types "
                "  WHERE name NOT IN ('Кроссовки', 'Кроссовки/кеды')"
                ")"
            ))
            await conn.execute(text(
                "UPDATE items "
                "SET is_legit = FALSE "
                "WHERE is_legit IS NULL"
            ))
            logger.info("Колонка is_legit инициализирована (оригинал / реплика)")
        
        # Миграция: добавление поля stock_type в cart
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'cart' AND column_name = 'stock_type')"
        ))
        stock_type_exists = result.scalar()
        
        if not stock_type_exists:
            logger.info("Добавляем колонку stock_type в таблицу cart...")
            await conn.execute(text("ALTER TABLE cart ADD COLUMN stock_type VARCHAR(20) NOT NULL DEFAULT 'preorder'"))
            logger.info("Колонка stock_type добавлена")
        
        # Удаляем старый уникальный индекс и создаем новый с учетом stock_type (если еще не создан)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'uq_cart_user_item_size_stock')"
        ))
        new_index_exists = result.scalar()
        
        if not new_index_exists:
            # Проверяем, существует ли старый constraint (не index!)
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.table_constraints "
                "WHERE constraint_name = 'uq_cart_user_item_size' AND table_name = 'cart')"
            ))
            old_constraint_exists = result.scalar()
            
            if old_constraint_exists:
                # Удаляем старый constraint (PostgreSQL создает индекс автоматически для unique constraint)
                await conn.execute(text("ALTER TABLE cart DROP CONSTRAINT IF EXISTS uq_cart_user_item_size"))
                logger.info("Старый unique constraint удален")
            
            # Проверяем, остался ли старый индекс после удаления constraint (иногда он остается)
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'uq_cart_user_item_size')"
            ))
            old_index_exists = result.scalar()
            
            if old_index_exists:
                await conn.execute(text("DROP INDEX IF EXISTS uq_cart_user_item_size"))
                logger.info("Старый индекс удален")
            
            # Создаем новый уникальный индекс с stock_type
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_cart_user_item_size_stock "
                "ON cart(user_id, item_id, COALESCE(size, ''), stock_type)"
            ))
            logger.info("Новый уникальный индекс с stock_type создан")
        
        # Миграция: orders — добавить tracking_number, recipient_name, удалить parent_order_id, username, order_platform, estimated_cost, delivery_method, delivery_address
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'orders' AND column_name = 'tracking_number')"
        ))
        tracking_number_exists = result.scalar()
        if not tracking_number_exists:
            logger.info("Добавляем колонку tracking_number в таблицу orders...")
            await conn.execute(text("ALTER TABLE orders ADD COLUMN tracking_number VARCHAR(255)"))
            await conn.execute(text(
                "COMMENT ON COLUMN orders.tracking_number IS "
                "'Трек-номер накладной (СДЭК и т.д.), заполняется при создании накладной'"
            ))
            logger.info("Колонка tracking_number добавлена")
        # Добавляем recipient_name (ФИО получателя для накладной), если ещё нет
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'orders' AND column_name = 'recipient_name')"
        ))
        recipient_name_exists = result.scalar()
        if not recipient_name_exists:
            logger.info("Добавляем колонку recipient_name в таблицу orders...")
            await conn.execute(text("ALTER TABLE orders ADD COLUMN recipient_name VARCHAR(255)"))
            await conn.execute(text(
                "COMMENT ON COLUMN orders.recipient_name IS "
                "'ФИО получателя для доставки/накладной'"
            ))
            logger.info("Колонка recipient_name добавлена")
        # hidden_from_user_at — скрытие заказа из списка пользователя (мягкое удаление)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'orders' AND column_name = 'hidden_from_user_at')"
        ))
        if not result.scalar():
            logger.info("Добавляем колонку hidden_from_user_at в таблицу orders...")
            await conn.execute(text("ALTER TABLE orders ADD COLUMN hidden_from_user_at TIMESTAMP WITH TIME ZONE"))
            logger.info("Колонка hidden_from_user_at добавлена")
        # Фиксированный whitelist колонок для удаления (не подставлять пользовательский ввод)
        orders_drop_columns_whitelist = (
            "parent_order_id", "username", "order_platform",
            "estimated_cost", "delivery_method", "delivery_address",
        )
        for col in orders_drop_columns_whitelist:
            col_exists = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'orders' AND column_name = :col)"
            ), {"col": col})
            if col_exists.scalar():
                logger.info("Удаляем колонку orders.%s...", col)
                await conn.execute(text("ALTER TABLE orders DROP COLUMN IF EXISTS " + col))
                logger.info("Колонка orders.%s удалена", col)

        # Реферальные поля в promocodes
        for col_name, col_sql in [
            ("referrer_user_id", "ALTER TABLE promocodes ADD COLUMN referrer_user_id INTEGER"),
            (
                "referral_commission_percent",
                "ALTER TABLE promocodes ADD COLUMN referral_commission_percent NUMERIC(5,2)",
            ),
        ]:
            exists = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'promocodes' AND column_name = :c)"
            ), {"c": col_name})
            if not exists.scalar():
                logger.info("Добавляем promocodes.%s...", col_name)
                await conn.execute(text(col_sql))
        result_ix = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = 'ix_promocodes_referrer_user_id')"
        ))
        if not result_ix.scalar():
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_promocodes_referrer_user_id ON promocodes(referrer_user_id)"
            ))

        for tbl, col in [
            ("promocodes", "pool_is_blacklist"),
            ("system_photo_promo_settings", "pool_is_blacklist"),
        ]:
            ex = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c)"
            ), {"t": tbl, "c": col})
            if not ex.scalar():
                logger.info("Добавляем %s.%s...", tbl, col)
                await conn.execute(
                    text(f"ALTER TABLE {tbl} ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT FALSE")
                )

        # Скидка за AI-примерки по заказу
        _tryon_order_cols = [
            ("tryon_discount_rub", "NUMERIC(10,2) NOT NULL DEFAULT 0"),
            ("tryon_discount_units_reserved", "INTEGER NOT NULL DEFAULT 0"),
            ("tryon_discount_bonus_credits", "INTEGER NOT NULL DEFAULT 0"),
            ("tryon_discount_settled", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ]
        for col_name, col_type in _tryon_order_cols:
            exists = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'orders' AND column_name = :c)"
            ), {"c": col_name})
            if not exists.scalar():
                logger.info("Добавляем orders.%s...", col_name)
                await conn.execute(
                    text(f"ALTER TABLE orders ADD COLUMN {col_name} {col_type}")
                )

        # Рекомендательный граф: профили стилей + совместимости
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_style_profiles')"
        ))
        if not result.scalar():
            logger.info("Создаём таблицу item_style_profiles...")
            await conn.execute(text("""
                CREATE TABLE item_style_profiles (
                    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
                    slot VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    item_type_name VARCHAR(100),
                    top_styles JSONB,
                    style_vector JSONB NOT NULL,
                    color_wheel_profile JSONB,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_item_style_profiles_slot ON item_style_profiles(slot)"))
            logger.info("✅ Таблица item_style_profiles создана")

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'item_compatibility_edges')"
        ))
        if not result.scalar():
            logger.info("Создаём таблицу item_compatibility_edges...")
            await conn.execute(text("""
                CREATE TABLE item_compatibility_edges (
                    from_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    to_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    score NUMERIC(10,6) NOT NULL,
                    style_score NUMERIC(10,6) NOT NULL,
                    color_score NUMERIC(10,6) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (from_item_id, to_item_id)
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_item_compatibility_edges_from_score ON item_compatibility_edges(from_item_id, score DESC)"))
            logger.info("✅ Таблица item_compatibility_edges создана")
        
        logger.info("Миграции выполнены успешно")
    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА при выполнении миграций: {e}", exc_info=True)
        # Пробрасываем исключение, чтобы запуск приложения прервался и мы увидели проблему
        raise RuntimeError(f"Не удалось выполнить миграции базы данных: {e}") from e

