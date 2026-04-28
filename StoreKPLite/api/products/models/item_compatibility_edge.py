from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from api.products.database.database import Base


class ItemCompatibilityEdge(Base):
    __tablename__ = "item_compatibility_edges"

    from_item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    to_item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    score = Column(Numeric(10, 6), nullable=False, index=True)
    style_score = Column(Numeric(10, 6), nullable=False)
    color_score = Column(Numeric(10, 6), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    from_item = relationship("Item", foreign_keys=[from_item_id])
    to_item = relationship("Item", foreign_keys=[to_item_id])
