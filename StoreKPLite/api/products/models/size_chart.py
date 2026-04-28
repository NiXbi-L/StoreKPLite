"""
Модель размерной сетки. Один размерная сетка может быть привязана к нескольким товарам.
"""
from sqlalchemy import Column, Integer, String, JSON
from api.products.database.database import Base


class SizeChart(Base):
    __tablename__ = "size_charts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="Название размерной сетки")
    # Таблица: массив строк, каждая строка — массив ячеек (строковые значения).
    # Пример: {"rows": [["Россия", "Грудь", "Талия"], ["42", "84-86", "66-68"], ["44", "88-90", "70-72"]]}
    grid = Column(JSON, nullable=False, comment="JSON: { \"rows\": [[\"cell\", ...], ...] }")
