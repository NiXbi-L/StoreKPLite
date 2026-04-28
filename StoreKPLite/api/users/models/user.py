"""
Модель пользователя
"""
from sqlalchemy import BigInteger, String, Column, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.users.database.database import Base


class User(Base):
    __tablename__ = "users"

    # Внутренний ID (используется всеми сервисами)
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="Внутренний ID пользователя")

    # Telegram (единственная платформа для мини-приложения)
    tgid = Column(BigInteger, unique=True, nullable=True, index=True, comment="Telegram User ID")
    firstname = Column(String(255), nullable=True, comment="Имя из Telegram (first_name)")
    username = Column(String(255), nullable=True, comment="Username из Telegram (@username)")

    # Контактные данные
    country_code = Column(String(10), nullable=True, comment="Код страны (например +7)")
    phone_local = Column(String(20), nullable=True, comment="Номер телефона без кода страны")
    email = Column(String(255), nullable=True, index=True, comment="Email")

    # Данные профиля
    gender = Column(String(10), nullable=True, comment="Пол: male или female")
    telegram_photo_url = Column(
        String(512), nullable=True, comment="URL фото профиля из Telegram (фолбек, без VPN может не открываться)"
    )
    profile_avatar_url = Column(
        String(512), nullable=True, comment="Аватар, загруженный пользователем в приложении (приоритет над Telegram)"
    )
    privacy_policy_accepted = Column(Boolean, nullable=False, default=False, comment="Согласие на обработку персональных данных")
    privacy_policy_accepted_at = Column(DateTime(timezone=True), nullable=True, comment="Дата принятия политики конфиденциальности")
    feed_onboarding_seen = Column(Boolean, nullable=False, default=False, comment="Обучение ленты (свайпы) пройдено")
    tryon_credits = Column(Integer, nullable=False, default=0, comment="Доступные AI-примерки (оплаченные)")
    tryon_generations_consumed_total = Column(
        Integer, nullable=False, default=0, comment="Всего успешных генераций (списаний примерок)"
    )
    tryon_generations_applied_to_orders = Column(
        Integer, nullable=False, default=0, comment="Генераций зачтено в завершённых заказах (скидка)"
    )
    tryon_profile_bonus_granted = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Бонус +1 примерка за заполненный профиль (телефон+пол) уже выдан",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата создания пользователя",
    )

    # Связи
    admins = relationship("Admin", back_populates="user", cascade="all, delete-orphan")

    def has_platform(self, platform: str) -> bool:
        """Проверить, привязан ли пользователь к платформе (только telegram)"""
        if platform == "telegram":
            return self.tgid is not None
        return False
