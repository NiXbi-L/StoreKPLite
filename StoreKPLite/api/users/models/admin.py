"""
Модель администратора
"""
from sqlalchemy import String, Column, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from api.users.database.database import Base


class Admin(Base):
    __tablename__ = "admins"
    
    # Используем внутренний ID пользователя как первичный ключ
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True, comment="Внутренний ID пользователя")
    
    admin_type = Column(
        String(20),
        nullable=False,
        comment="Только owner (вход Owner) или staff (права из admin_roles или legacy permissions_json)",
    )
    role_id = Column(
        Integer,
        ForeignKey("admin_roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Роль сотрудника (права из admin_roles)",
    )
    role_title = Column(String(80), nullable=True, comment="Legacy: подпись если нет role_id")
    permissions_json = Column(Text, nullable=True, comment="Legacy: права на строке, если role_id пуст")
    login = Column(String(50), unique=True, nullable=True, comment="Логин для веб-админки")
    password = Column(String(255), nullable=True, comment="Пароль для веб-админки (хэш)")
    
    user = relationship("User", back_populates="admins")
    assigned_role = relationship("AdminRole", back_populates="admins")

