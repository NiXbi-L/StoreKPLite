"""Сырые продуктовые события из мини-приложения (батчи с фронта)."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, func

from api.users.database.database import Base


class MiniappProductEvent(Base):
    """Одно событие из батча POST /users/me/product-analytics/batch."""

    __tablename__ = "miniapp_product_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(40), nullable=False, index=True)
    client_session_id = Column(String(40), nullable=False, index=True)
    event_name = Column(String(128), nullable=False, index=True)
    payload_json = Column(Text, nullable=False, server_default="{}")
    client_ts_ms = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
