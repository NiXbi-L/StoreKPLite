from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from api.products.database.database import Base


class ItemStyleProfile(Base):
    __tablename__ = "item_style_profiles"

    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    slot = Column(String(32), nullable=False, index=True, default="unknown")
    item_type_name = Column(String(100), nullable=True)
    top_styles = Column(JSON, nullable=True)
    style_vector = Column(JSON, nullable=False)
    color_wheel_profile = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    item = relationship("Item")
