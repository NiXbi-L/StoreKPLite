"""
Модель тикета поддержки
"""
from sqlalchemy import String, Column, Integer, Text, JSON, DateTime
from sqlalchemy.sql import func
from api.support.database.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # Используем внутренний ID пользователя вместо tgid
    user_id = Column(Integer, nullable=True, index=True, comment="Внутренний ID пользователя из сервиса users")
    username = Column(String(255), nullable=True, comment="Username пользователя на момент обращения")
    text = Column(Text, nullable=False, comment="Текст обращения пользователя")
    photos = Column(JSON, nullable=True, comment="Список путей к фото обращения в формате JSON")
    status = Column(
        String(20),
        nullable=False,
        default="Ожидает",
        comment="Статус тикета: Ожидает, в работе, закрыт",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания тикета")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления тикета")

