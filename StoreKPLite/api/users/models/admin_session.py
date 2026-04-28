"""
Активные сессии админки (по устройствам/браузерам).
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from api.users.database.database import Base


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("admins.user_id", ondelete="CASCADE"), nullable=False, index=True)
    sid = Column(String(64), nullable=False, unique=True, index=True, comment="Session ID в JWT (sid)")
    user_agent = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

