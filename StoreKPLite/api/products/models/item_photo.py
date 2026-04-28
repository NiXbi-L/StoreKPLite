"""
Модель фотографии товара
"""
from sqlalchemy import String, Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemPhoto(Base):
    __tablename__ = "item_photos"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID вещи")
    file_path = Column(String(500), nullable=False, comment="Путь к файлу фотографии")
    telegram_file_id = Column(String(255), nullable=True, index=True, comment="Telegram file_id для быстрой отправки")
    vk_attachment = Column(String(255), nullable=True, index=True, comment="VK attachment для быстрой отправки")
    sort_order = Column(Integer, nullable=False, default=0, index=True, comment="Порядок сортировки фотографий")
    
    # Связь с вещью
    item = relationship("Item", back_populates="photos")

