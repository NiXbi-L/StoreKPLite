"""
Модель отзыва о товаре: дата, оценка 1–5, user_id, item_id, комментарий, до 10 фото.
"""
from sqlalchemy import String, Column, Integer, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from api.products.database.database import Base


class ItemReview(Base):
    __tablename__ = "item_reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1–5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    photos = relationship("ItemReviewPhoto", back_populates="review", cascade="all, delete-orphan", order_by="ItemReviewPhoto.sort_order")


class ItemReviewPhoto(Base):
    __tablename__ = "item_review_photos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    review_id = Column(Integer, ForeignKey("item_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    review = relationship("ItemReview", back_populates="photos")
