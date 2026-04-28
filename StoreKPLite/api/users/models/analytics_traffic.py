"""Агрегаты трафика из nginx и снимки онлайна."""
from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from api.users.database.database import Base


class TrafficAnalyticsDaily(Base):
    """Один день (по дате в access.log): доли miniapp / веб и пики по часам."""

    __tablename__ = "traffic_analytics_daily"
    __table_args__ = (UniqueConstraint("period_date", name="uq_traffic_analytics_daily_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    period_date = Column(Date, nullable=False, index=True)
    miniapp_requests = Column(Integer, nullable=False, server_default="0")
    web_mobile_requests = Column(Integer, nullable=False, server_default="0")
    web_desktop_requests = Column(Integer, nullable=False, server_default="0")
    web_unknown_requests = Column(Integer, nullable=False, server_default="0")
    # 24 числа — все запросы (миниапп + веб), час по часовому поясу из лога nginx
    hourly_total_json = Column(Text, nullable=False)
    # Только веб (не /miniapp/): ISO-код страны -> число запросов
    country_web_json = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NginxLogIngestState(Base):
    """Состояние чтения access.log (одна строка id=1)."""

    __tablename__ = "nginx_log_ingest_state"
    __table_args__ = ()

    id = Column(Integer, primary_key=True, default=1)
    log_path = Column(String(1024), nullable=False, default="")
    byte_offset = Column(BigInteger, nullable=False, server_default="0")
    file_inode = Column(BigInteger, nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    lines_processed_total = Column(BigInteger, nullable=False, server_default="0")


class OnlineSnapshot(Base):
    """Периодический снимок числа пользователей «онлайн» (heartbeat)."""

    __tablename__ = "online_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    online_count = Column(Integer, nullable=False, server_default="0")
