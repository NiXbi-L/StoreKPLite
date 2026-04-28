"""
Настройка базы данных для сервиса финансов
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from os import getenv

DATABASE_URL = getenv(
    "FINANCE_DATABASE_URL",
    getenv("DATABASE_URL", "postgresql+asyncpg://timoshka_user:timoshka_password@postgres:5432/timoshka_finance")
)

_engine_echo = getenv("FINANCE_SQL_ECHO", getenv("SQL_ECHO", "0")).lower() in (
    "1",
    "true",
    "yes",
)
engine = create_async_engine(DATABASE_URL, echo=_engine_echo)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


from fastapi import Depends
from typing import AsyncGenerator

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Инициализация базы данных"""
    from api.finance.models import (  # noqa: F401
        FinancialTransaction, AccountBalance, AccountTransaction,
        FinanceSettings, Sale, ExchangeRate, CurrencyTransfer, Payment, RefundLog, TryonPayment,
    )
    
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
        
        # Выполняем миграции для существующих таблиц
        await run_migrations(conn)


async def run_migrations(conn):
    """Выполнить SQL миграции для существующих таблиц"""
    import logging
    from sqlalchemy import text
    logger = logging.getLogger(__name__)
    
    try:
        # Миграция: удаление старых транзакций и добавление поля is_archived
        # Проверяем, существует ли таблица financial_transactions
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'financial_transactions')"
        ))
        table_exists = result.scalar()
        
        if table_exists:
            # Проверяем, существует ли колонка is_archived
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'financial_transactions' AND column_name = 'is_archived')"
            ))
            is_archived_exists = result.scalar()
            
            if not is_archived_exists:
                logger.info("Удаляем все старые транзакции...")
                # Удаляем все записи из financial_transactions
                delete_result = await conn.execute(text("DELETE FROM financial_transactions"))
                deleted_count = delete_result.rowcount if hasattr(delete_result, 'rowcount') else 0
                logger.info(f"Удалено старых транзакций: {deleted_count}")
                
                logger.info("Добавляем колонку is_archived в таблицу financial_transactions...")
                # Добавляем колонку is_archived
                await conn.execute(text(
                    "ALTER TABLE financial_transactions "
                    "ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE"
                ))
                logger.info("Колонка is_archived добавлена")
            else:
                logger.info("Колонка is_archived уже существует, миграция не требуется")

            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.columns "
                "WHERE table_name = 'financial_transactions' AND column_name = 'weight_kg')"
            ))
            weight_kg_exists = result.scalar()
            if not weight_kg_exists:
                logger.info("Добавляем колонку weight_kg в таблицу financial_transactions...")
                await conn.execute(text(
                    "ALTER TABLE financial_transactions "
                    "ADD COLUMN weight_kg NUMERIC(10,3)"
                ))
                await conn.execute(text(
                    "COMMENT ON COLUMN financial_transactions.weight_kg IS 'Вес поставки в килограммах'"
                ))
                logger.info("Колонка weight_kg добавлена")
        
        # Таблица логов возвратов (рефаундов)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'refund_logs')"
        ))
        refund_logs_exists = result.scalar()
        if not refund_logs_exists:
            logger.info("Создаём таблицу refund_logs...")
            await conn.execute(text(
                "CREATE TABLE refund_logs ("
                "id SERIAL PRIMARY KEY, "
                "order_id INTEGER NOT NULL, "
                "payment_id INTEGER NOT NULL REFERENCES payments(id), "
                "amount NUMERIC(10,2) NOT NULL, "
                "reason TEXT, "
                "yookassa_refund_id VARCHAR(255), "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
                ")"
            ))
            await conn.execute(text("CREATE INDEX ix_refund_logs_order_id ON refund_logs(order_id)"))
            await conn.execute(text("CREATE INDEX ix_refund_logs_payment_id ON refund_logs(payment_id)"))
            logger.info("Таблица refund_logs создана")

        # Цена примерки в finance_settings
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'finance_settings' AND column_name = 'tryon_unit_price_rub')"
        ))
        if not result.scalar():
            logger.info("Добавляем finance_settings.tryon_unit_price_rub...")
            await conn.execute(text(
                "ALTER TABLE finance_settings ADD COLUMN tryon_unit_price_rub NUMERIC(10,2)"
            ))
            await conn.execute(text(
                "COMMENT ON COLUMN finance_settings.tryon_unit_price_rub IS 'Цена одной AI-примерки в рублях'"
            ))

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tryon_payments')"
        ))
        if result.scalar():
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'tryon_payments' AND column_name = 'credits_granted')"
            ))
            if not result.scalar():
                logger.info("Добавляем tryon_payments.credits_granted...")
                await conn.execute(text(
                    "ALTER TABLE tryon_payments ADD COLUMN credits_granted BOOLEAN NOT NULL DEFAULT FALSE"
                ))

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'finance_settings' "
            "AND column_name = 'tryon_max_discount_units_per_item')"
        ))
        if not result.scalar():
            logger.info("Добавляем finance_settings.tryon_max_discount_units_per_item...")
            await conn.execute(text(
                "ALTER TABLE finance_settings ADD COLUMN tryon_max_discount_units_per_item SMALLINT NOT NULL DEFAULT 3"
            ))
            await conn.execute(text(
                "COMMENT ON COLUMN finance_settings.tryon_max_discount_units_per_item IS "
                "'Макс. генераций примерки в зачёт скидки на 1 единицу товара в заказе'"
            ))

        for col_name, col_sql, cmt in [
            (
                "yuan_markup_before_rub_percent",
                "ALTER TABLE finance_settings ADD COLUMN yuan_markup_before_rub_percent NUMERIC(5,2) NOT NULL DEFAULT 0",
                "Процент к юаням до перевода в рубли",
            ),
            (
                "customer_price_acquiring_factor",
                "ALTER TABLE finance_settings ADD COLUMN customer_price_acquiring_factor NUMERIC(5,4) NOT NULL DEFAULT 0.97",
                "Доля после эквайринга; цена клиента = сумма / это значение",
            ),
        ]:
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'finance_settings' "
                "AND column_name = :c)"
            ), {"c": col_name})
            if not result.scalar():
                logger.info("Добавляем finance_settings.%s...", col_name)
                await conn.execute(text(col_sql))
                await conn.execute(
                    text(f"COMMENT ON COLUMN finance_settings.{col_name} IS '{cmt}'")
                )

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'payments')"
        ))
        if result.scalar():
            for col, ddl in [
                ("receipt_registration", "VARCHAR(64)"),
                ("yookassa_receipt_id", "VARCHAR(255)"),
                ("receipt_items_json", "JSON"),
            ]:
                r2 = await conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'payments' "
                    f"AND column_name = '{col}')"
                ))
                if not r2.scalar():
                    logger.info(f"Добавляем payments.{col}...")
                    await conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col} {ddl}"))

            r_idx = await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = 'ix_payments_yookassa_receipt_id')"
            ))
            if not r_idx.scalar():
                logger.info("Создаём индекс ix_payments_yookassa_receipt_id...")
                await conn.execute(text(
                    "CREATE INDEX ix_payments_yookassa_receipt_id ON payments (yookassa_receipt_id)"
                ))

            for col_name, col_sql, cmt in [
                ("ofd_receipt_url", "TEXT", "Публичная ссылка на кассовый документ (Первый ОФД)"),
                (
                    "ofd_receipt_telegram_sent",
                    "BOOLEAN NOT NULL DEFAULT FALSE",
                    "Ссылка ОФД отправлена пользователю в Telegram",
                ),
            ]:
                r_ofd = await conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'payments' "
                    "AND column_name = :c)"
                ), {"c": col_name})
                if not r_ofd.scalar():
                    logger.info("Добавляем payments.%s...", col_name)
                    await conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col_name} {col_sql}"))
                    await conn.execute(
                        text(f"COMMENT ON COLUMN payments.{col_name} IS '{cmt}'")
                    )

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tryon_payments')"
        ))
        if result.scalar():
            for col_name, col_sql, cmt in [
                ("ofd_receipt_url", "TEXT", "Публичная ссылка на кассовый документ (Первый ОФД)"),
                (
                    "ofd_receipt_telegram_sent",
                    "BOOLEAN NOT NULL DEFAULT FALSE",
                    "Ссылка ОФД отправлена в Telegram",
                ),
            ]:
                r_ofd = await conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'tryon_payments' "
                    "AND column_name = :c)"
                ), {"c": col_name})
                if not r_ofd.scalar():
                    logger.info("Добавляем tryon_payments.%s...", col_name)
                    await conn.execute(text(f"ALTER TABLE tryon_payments ADD COLUMN {col_name} {col_sql}"))
                    await conn.execute(
                        text(f"COMMENT ON COLUMN tryon_payments.{col_name} IS '{cmt}'")
                    )

        for col_name, col_sql, cmt in [
            (
                "tryon_generation_internal_cost_rub",
                "ALTER TABLE finance_settings ADD COLUMN tryon_generation_internal_cost_rub NUMERIC(10,2)",
                "Учётная себестоимость одной примерки (₽)",
            ),
            (
                "tryon_clothing_profit_to_api_reserve_percent",
                "ALTER TABLE finance_settings ADD COLUMN tryon_clothing_profit_to_api_reserve_percent NUMERIC(5,2)",
                "Доля прибыли с одежды на резерв GenAPI (%)",
            ),
        ]:
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'finance_settings' "
                "AND column_name = :c)"
            ), {"c": col_name})
            if not result.scalar():
                logger.info("Добавляем finance_settings.%s...", col_name)
                await conn.execute(text(col_sql))
                await conn.execute(
                    text(f"COMMENT ON COLUMN finance_settings.{col_name} IS '{cmt}'")
                )

        result = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'account_balances')"
        ))
        if result.scalar():
            await conn.execute(text(
                "INSERT INTO account_balances (account_type, balance, updated_at) "
                "SELECT 'neural_api_reserve', 0, NOW() "
                "WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_type = 'neural_api_reserve')"
            ))

        logger.info("Миграции finance-service выполнены успешно")
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграций finance-service: {e}", exc_info=True)
        # Не прерываем запуск, если миграция не удалась
        # (возможно, миграция уже выполнена или есть другая проблема)

