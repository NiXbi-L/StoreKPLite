"""Преднастроенные роли админки (набор прав); сотруднику назначается role_id."""

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from api.users.database.database import Base


class AdminRole(Base):
    __tablename__ = "admin_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="Название роли в UI")
    permissions_json = Column(Text, nullable=False, comment="JSON прав (ключи ALL_ADMIN_PERMISSION_KEYS)")

    admins = relationship("Admin", back_populates="assigned_role")
