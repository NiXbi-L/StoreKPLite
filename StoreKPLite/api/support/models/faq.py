"""
Модель FAQ
"""
from sqlalchemy import String, Column, Integer, Text, DateTime
from sqlalchemy.sql import func
from api.support.database.database import Base


class FAQ(Base):
    __tablename__ = "faq"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, comment="Краткий заголовок вопроса")
    body = Column(Text, nullable=False, comment="Текст ответа/подсказки")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания записи")

