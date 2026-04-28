"""
Модель товара
"""
from sqlalchemy import String, Column, Integer, Numeric, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class Item(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="Название вещи")
    chinese_name = Column(String(255), nullable=True, comment="Название вещи на китайском (опционально)")
    description = Column(Text, nullable=True, comment="Описание")
    price = Column(Numeric(10, 2), nullable=False, comment="Цена в юанях")
    service_fee_percent = Column(Numeric(5, 2), nullable=False, default=0, comment="Процент сервисного сбора от итоговой цены (юань на курс)")
    estimated_weight_kg = Column(Numeric(5, 2), nullable=True, comment="Ориентировочный вес посылки в кг")
    length_cm = Column(Integer, nullable=True, comment="Длина посылки (см), для расчёта доставки")
    width_cm = Column(Integer, nullable=True, comment="Ширина посылки (см)")
    height_cm = Column(Integer, nullable=True, comment="Высота посылки (см)")
    item_type_id = Column(Integer, ForeignKey("item_types.id", ondelete="RESTRICT"), nullable=False, index=True, comment="ID типа вещи")
    gender = Column(String(20), nullable=False, comment="Пол: М, Ж, унисекс")
    size = Column(JSON, nullable=True, comment="Размеры (массив строк)")
    link = Column(String(500), nullable=True, comment="Ссылка на товар")
    group_id = Column(Integer, ForeignKey("item_groups.id", ondelete="SET NULL"), nullable=True, index=True, comment="ID группы товаров")
    size_chart_id = Column(Integer, ForeignKey("size_charts.id", ondelete="SET NULL"), nullable=True, index=True, comment="ID размерной сетки")
    is_legit = Column(Boolean, nullable=True, comment="Оригинал (легит) = True, реплика = False")
    fixed_price = Column(Numeric(10, 2), nullable=True, comment="Фиксированная цена в рублях (для товара в наличии)")
    tags = Column(JSON, nullable=True, comment="Теги для поиска (массив строк), например: Офвайт, Спонж мид топ")
    
    # Связи
    photos = relationship("ItemPhoto", back_populates="item", cascade="all, delete-orphan")
    stock = relationship("ItemStock", back_populates="item", cascade="all, delete-orphan")
    reservations = relationship("ItemReservation", back_populates="item", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="item", cascade="all, delete-orphan")
    cart_items = relationship("Cart", back_populates="item", cascade="all, delete-orphan")
    price_history = relationship("ItemPriceHistory", back_populates="item", cascade="all, delete-orphan")
    group = relationship("ItemGroup", back_populates="items")
    size_chart = relationship("SizeChart", backref="items")
    item_type_rel = relationship("ItemType", back_populates="items")

