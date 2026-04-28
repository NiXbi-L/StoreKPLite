"""Глобальные переключатели сервиса (одна строка id=1)."""
from sqlalchemy import Boolean, Column, Integer, Text
from sqlalchemy.schema import CheckConstraint

from api.users.database.database import Base


class AppRuntimeSettings(Base):
    __tablename__ = "app_runtime_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="app_runtime_settings_single_row"),
    )

    id = Column(Integer, primary_key=True, default=1)
    miniapp_admin_only = Column(Boolean, nullable=False, server_default="false")
    miniapp_guest_html = Column(Text, nullable=True)
