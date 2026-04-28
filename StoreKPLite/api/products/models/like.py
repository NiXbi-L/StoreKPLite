"""
Модель лайка/дизлайка
"""
from sqlalchemy import String, Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class Like(Base):
    __tablename__ = "likes"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # Используем внутренний ID пользователя вместо tgid
    user_id = Column(Integer, nullable=False, index=True, comment="Внутренний ID пользователя из сервиса users")
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID вещи")
    action = Column(
        String(20),
        nullable=False,
        comment="Действие: like (лайк), dislike (дизлайк), save (отложить)"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания")
    
    # Уникальный индекс на комбинацию user_id + item_id
    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', name='uq_user_item'),
    )
    
    # Связи
    item = relationship("Item", back_populates="likes")

