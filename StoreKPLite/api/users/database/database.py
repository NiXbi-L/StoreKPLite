"""
Настройка базы данных для сервиса пользователей
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from os import getenv

# URL базы данных для сервиса пользователей
# Можно использовать отдельную БД или общую с префиксом users_
DATABASE_URL = getenv(
    "USERS_DATABASE_URL",
    getenv("DATABASE_URL", "postgresql+asyncpg://timoshka_user:timoshka_password@postgres:5432/timoshka_users")
)

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


from typing import AsyncGenerator
import json
import logging

logger_db = logging.getLogger(__name__)


async def apply_admin_roles_schema_isolated() -> None:
    """
    Таблица admin_roles и колонка admins.role_id — в отдельной транзакции.
    Иначе при ошибке/откате длинного init_db() (например UPDATE по users) DDL не закрепляется,
    а сервис всё равно поднимается — и ORM падает с «column role_id does not exist».
    """
    async with engine.begin() as conn:
        # asyncpg: одна команда на execute (нельзя CREATE + COMMENT в одной строке)
        await conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS admin_roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                permissions_json TEXT NOT NULL
            )
            """)
        )
        await conn.execute(
            text(
                "COMMENT ON TABLE admin_roles IS 'Роли админки: набор прав; сотруднику назначается role_id'"
            )
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'admins'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'admins'
                      AND column_name = 'role_id'
                ) THEN
                    ALTER TABLE admins ADD COLUMN role_id INTEGER
                        REFERENCES admin_roles(id) ON DELETE SET NULL;
                    CREATE INDEX IF NOT EXISTS ix_admins_role_id ON admins(role_id);
                    COMMENT ON COLUMN admins.role_id IS 'Роль сотрудника (права из admin_roles)';
                END IF;
            END$$;
            """)
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Инициализация базы данных"""
    # Импорт всех моделей для регистрации в метаданных
    from api.users.models import User, Admin, AdminRole, AdminSession  # noqa: F401
    from api.users.models.tryon_order_discount_reservation import TryonOrderDiscountReservation  # noqa: F401
    from api.users.models.app_runtime_settings import AppRuntimeSettings  # noqa: F401
    from api.users.models.analytics_traffic import (  # noqa: F401
        TrafficAnalyticsDaily,
        NginxLogIngestState,
        OnlineSnapshot,
    )
    from api.users.models.miniapp_product_event import MiniappProductEvent  # noqa: F401

    # Сначала коммитим DDL ролей отдельно (см. docstring apply_admin_roles_schema_isolated).
    await apply_admin_roles_schema_isolated()

    async with engine.begin() as conn:
        # Создаем все таблицы (если не созданы)
        await conn.run_sync(Base.metadata.create_all)
        # Простейшие миграции
        # 1) Добавить avatar_url в таблицу users, если ещё нет
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'avatar_url'
                ) THEN
                    ALTER TABLE users ADD COLUMN avatar_url VARCHAR(512);
                    COMMENT ON COLUMN users.avatar_url IS 'URL аватарки пользователя (Telegram photo_url или наш CDN)';
                END IF;
            END$$;
            """)
        )
        # 1b) Аватар: telegram_photo_url + profile_avatar_url, миграция с legacy avatar_url
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'telegram_photo_url'
                ) THEN
                    ALTER TABLE users ADD COLUMN telegram_photo_url VARCHAR(512);
                    COMMENT ON COLUMN users.telegram_photo_url IS 'URL фото из Telegram (фолбек)';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'profile_avatar_url'
                ) THEN
                    ALTER TABLE users ADD COLUMN profile_avatar_url VARCHAR(512);
                    COMMENT ON COLUMN users.profile_avatar_url IS 'Аватар загруженный в приложении';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'avatar_url'
                ) THEN
                    UPDATE users SET telegram_photo_url = COALESCE(telegram_photo_url, avatar_url)
                    WHERE avatar_url IS NOT NULL;
                    ALTER TABLE users DROP COLUMN avatar_url;
                END IF;
            END$$;
            """)
        )
        # 2) Добавить firstname и username в таблицу users, если ещё нет
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'firstname'
                ) THEN
                    ALTER TABLE users ADD COLUMN firstname VARCHAR(255);
                    COMMENT ON COLUMN users.firstname IS 'Имя из Telegram (first_name)';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'username'
                ) THEN
                    ALTER TABLE users ADD COLUMN username VARCHAR(255);
                    COMMENT ON COLUMN users.username IS 'Username из Telegram (@username)';
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tryon_credits'
                ) THEN
                    ALTER TABLE users ADD COLUMN tryon_credits INTEGER NOT NULL DEFAULT 0;
                    COMMENT ON COLUMN users.tryon_credits IS 'Доступные AI-примерки (оплаченные)';
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tryon_generations_consumed_total'
                ) THEN
                    ALTER TABLE users ADD COLUMN tryon_generations_consumed_total INTEGER NOT NULL DEFAULT 0;
                    COMMENT ON COLUMN users.tryon_generations_consumed_total IS 'Всего успешных генераций (списаний примерок)';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tryon_generations_applied_to_orders'
                ) THEN
                    ALTER TABLE users ADD COLUMN tryon_generations_applied_to_orders INTEGER NOT NULL DEFAULT 0;
                    COMMENT ON COLUMN users.tryon_generations_applied_to_orders IS 'Генераций зачтено в завершённых заказах (скидка)';
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.tables WHERE table_name = 'tryon_order_discount_reservations'
                ) THEN
                    CREATE TABLE tryon_order_discount_reservations (
                        order_id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        units_reserved INTEGER NOT NULL,
                        bonus_credits_on_complete INTEGER NOT NULL DEFAULT 0,
                        discount_rub NUMERIC(10,2) NOT NULL DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX ix_tryon_order_discount_reservations_user_id
                        ON tryon_order_discount_reservations(user_id);
                    COMMENT ON TABLE tryon_order_discount_reservations IS 'Резерв генераций под скидку по заказу (до завершения)';
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables WHERE table_name = 'tryon_order_discount_reservations'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'tryon_order_discount_reservations' AND column_name = 'discount_rub'
                ) THEN
                    ALTER TABLE tryon_order_discount_reservations ADD COLUMN discount_rub NUMERIC(10,2) NOT NULL DEFAULT 0;
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tryon_profile_bonus_granted'
                ) THEN
                    ALTER TABLE users ADD COLUMN tryon_profile_bonus_granted BOOLEAN NOT NULL DEFAULT FALSE;
                    COMMENT ON COLUMN users.tryon_profile_bonus_granted IS
                        'Бонус +1 примерка за профиль (телефон+пол) уже выдан';
                END IF;
            END$$;
            """)
        )
        await conn.execute(
            text("""
            UPDATE users SET
                tryon_credits = COALESCE(tryon_credits, 0) + 1,
                tryon_profile_bonus_granted = TRUE
            WHERE tryon_profile_bonus_granted = FALSE
              AND phone_local IS NOT NULL
              AND LENGTH(TRIM(phone_local)) > 0
              AND LOWER(TRIM(gender)) IN ('male', 'female');
            """)
        )
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'admins' AND column_name = 'role_title'
                ) THEN
                    ALTER TABLE admins ADD COLUMN role_title VARCHAR(80);
                    COMMENT ON COLUMN admins.role_title IS 'Отображаемое имя роли сотрудника';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'admins' AND column_name = 'permissions_json'
                ) THEN
                    ALTER TABLE admins ADD COLUMN permissions_json TEXT;
                    COMMENT ON COLUMN admins.permissions_json IS 'JSON гранулярных прав';
                END IF;
            END$$;
            """)
        )

    await ensure_app_runtime_settings_row()


async def ensure_app_runtime_settings_row() -> None:
    """Одна строка настроек (id=1) для режима miniapp admin-only и HTML гостям."""
    from api.users.models.app_runtime_settings import AppRuntimeSettings

    async with async_session_maker() as session:
        row = await session.get(AppRuntimeSettings, 1)
        if row is None:
            session.add(AppRuntimeSettings(id=1, miniapp_admin_only=False))
            await session.commit()
            logger_db.info("Создана строка app_runtime_settings (id=1)")


async def ensure_admin_roles_seeded():
    """Три стандартные роли (как legacy admin/moderator/support), если таблица пуста."""
    from sqlalchemy import select, func
    from api.users.models.admin_role import AdminRole
    from api.shared.admin_permissions import LEGACY_ROLE_TITLE, legacy_defaults_for

    async with async_session_maker() as session:
        n = await session.scalar(select(func.count()).select_from(AdminRole))
        if n and n > 0:
            return
        for old_key in ("admin", "moderator", "support"):
            name = LEGACY_ROLE_TITLE[old_key]
            perms = legacy_defaults_for(old_key)
            session.add(
                AdminRole(
                    name=name,
                    permissions_json=json.dumps(perms, ensure_ascii=False),
                )
            )
        await session.commit()
        logger_db.info("Созданы стандартные роли admin_roles (3 шт.)")


async def migrate_legacy_admin_roles_to_staff():
    """admin/moderator/support -> staff + привязка к admin_roles по имени."""
    from sqlalchemy import select
    from api.users.models.admin import Admin
    from api.users.models.admin_role import AdminRole
    from api.shared.admin_permissions import LEGACY_ROLE_TITLE

    async with async_session_maker() as session:
        roles_result = await session.execute(select(AdminRole))
        by_name = {r.name: r for r in roles_result.scalars().all()}
        if not by_name:
            return

        result = await session.execute(
            select(Admin).where(Admin.admin_type.in_(["admin", "moderator", "support"]))
        )
        rows = result.scalars().all()
        if not rows:
            return
        for a in rows:
            old = (a.admin_type or "").strip().lower()
            title = LEGACY_ROLE_TITLE.get(old)
            role = by_name.get(title) if title else None
            a.admin_type = "staff"
            if role:
                a.role_id = role.id
                a.permissions_json = None
                a.role_title = None
            else:
                from api.shared.admin_permissions import legacy_defaults_for

                if title:
                    perms = legacy_defaults_for(old)
                    a.permissions_json = json.dumps(perms, ensure_ascii=False)
                    a.role_title = title
                logger_db.warning(
                    "Нет роли %s в admin_roles, fallback JSON для user_id=%s",
                    title,
                    a.user_id,
                )
        await session.commit()
        logger_db.info("Миграция ролей админов: %s записей -> staff + role_id", len(rows))


async def backfill_staff_role_id_from_legacy_json():
    """staff с заполненным permissions_json и пустым role_id — подобрать совпадающую admin_roles."""
    from sqlalchemy import select
    from api.users.models.admin import Admin
    from api.users.models.admin_role import AdminRole

    async with async_session_maker() as session:
        roles = (await session.execute(select(AdminRole))).scalars().all()
        if not roles:
            return
        staff = (
            await session.execute(
                select(Admin).where(
                    Admin.admin_type == "staff",
                    Admin.role_id.is_(None),
                    Admin.permissions_json.isnot(None),
                )
            )
        ).scalars().all()
        if not staff:
            return
        updated = 0
        for a in staff:
            raw = (a.permissions_json or "").strip()
            if not raw:
                continue
            for r in roles:
                if (r.permissions_json or "").strip() == raw:
                    a.role_id = r.id
                    a.permissions_json = None
                    a.role_title = None
                    updated += 1
                    break
        if updated:
            await session.commit()
            logger_db.info("backfill_staff_role_id: привязано %s сотрудников к ролям по JSON", updated)

