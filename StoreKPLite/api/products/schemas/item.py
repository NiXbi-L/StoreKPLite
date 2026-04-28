"""
Pydantic схемы для товаров
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel

from api.products.schemas.size_chart import SizeChartResponse


class InCartEntry(BaseModel):
    """Одна позиция этого товара в корзине пользователя (при авторизованном запросе)"""
    size: Optional[str] = None  # None или "" для товара без размера
    quantity: int
    stock_type: str  # "in_stock" | "preorder"
    cart_item_id: int


class ItemPhotoResponse(BaseModel):
  id: int
  file_path: str
  telegram_file_id: Optional[str] = None
  vk_attachment: Optional[str] = None
  sort_order: Optional[int] = 0


class ItemResponse(BaseModel):
  id: int
  name: str
  chinese_name: Optional[str] = None
  description: Optional[str]
  price: Decimal
  service_fee_percent: Decimal
  estimated_weight_kg: Optional[Decimal]
  length_cm: Optional[int] = None
  width_cm: Optional[int] = None
  height_cm: Optional[int] = None
  item_type_id: int
  item_type: Optional[str] = None  # Название типа для обратной совместимости
  gender: str
  size: Optional[List[str]]
  link: Optional[str]
  group_id: Optional[int] = None
  size_chart_id: Optional[int] = None
  size_chart: Optional[SizeChartResponse] = None
  photos: List[ItemPhotoResponse] = []
  price_rub: Optional[Decimal] = None  # Цена в рублях (расчитанная, итог для клиента)
  service_fee_amount: Optional[Decimal] = None  # Наценка (руб) из итоговой цены — для отображения в списке каталога
  is_legit: Optional[bool] = None  # True — оригинал (легит), False — реплика
  fixed_price: Optional[Decimal] = None  # Фиксированная цена в рублях (настраивается в админке)
  tags: Optional[List[str]] = None  # Теги для поиска (Офвайт, Спонж мид топ и т.д.)
  feed_like_count: int = 0  # Лайки ленты (таблица likes, action=like)
  feed_dislike_count: int = 0  # Дизлайки ленты (action=dislike)


class PriceHistoryPoint(BaseModel):
  week_start: datetime
  min_price: Decimal
  max_price: Decimal
  avg_price: Optional[Decimal] = None  # Средняя за период (для графика; за день или за 4h)


class FeedItemResponse(BaseModel):
  """Ответ для ленты - карточка товара и детальной карточки"""
  id: int
  name: str
  chinese_name: Optional[str] = None
  description: Optional[str]
  item_type: Optional[str] = None  # Название типа (худи, джинсы…) — для фильтров и примерки
  item_type_id: Optional[int] = None
  price_rub: Decimal  # Итоговая цена в рублях (для предзаказа)
  size: Optional[str]  # Размеры как строка через запятую (для отображения в ботах)
  min_price_week: Optional[Decimal]  # Минимальная цена за неделю
  max_price_week: Optional[Decimal]  # Максимальная цена за неделю
  telegram_file_id: Optional[str]  # file_id первого фото для Telegram
  vk_attachment: Optional[str]  # attachment для VK
  photos: List[ItemPhotoResponse] = []
  group_id: Optional[int] = None  # ID группы товаров
  group_name: Optional[str] = None  # Название группы
  group_items: Optional[List["FeedItemResponse"]] = []  # Все товары в группе (включая текущий)
  is_group: bool = False  # Флаг, что это группа товаров
  is_legit: Optional[bool] = None  # True — оригинал (легит), False — реплика
  price_history: Optional[List[PriceHistoryPoint]] = None  # Полная история цен (по неделям, детальная карточка)
  liked: Optional[bool] = None  # Лайкнул ли пользователь товар (для авторизованных запросов)
  fixed_price_rub: Optional[Decimal] = None  # Фиксированная цена в рублях; отдаётся только если есть остаток хотя бы по одному размеру
  in_cart: Optional[List[InCartEntry]] = None  # Позиции этого товара в корзине (размер, кол-во, stock_type, cart_item_id) — только при авторизованном запросе
  size_chart: Optional[SizeChartResponse] = None  # Размерная сетка (таблица размеров)
  photo_promo_badge: Optional[str] = None  # Бейдж системного фото-промо (если активен и слот по товару свободен)
  feed_like_count: int = 0  # Сколько пользователей сейчас с action=like в ленте
  feed_dislike_count: int = 0  # Сколько с action=dislike


class CatalogPageResponse(BaseModel):
  """Ответ пагинированного каталога для мини-аппа"""
  items: List[FeedItemResponse]
  total: int
  has_more: bool
  next_offset: Optional[int] = None


class LikesSummaryResponse(BaseModel):
  """Сводка по полке лайков: число и ревизия для кеша на клиенте."""
  total: int
  rev: int


class ItemGroupByItemResponse(BaseModel):
  """Ответ: карточки группы по конкретной вещи или признак «не в группе»"""
  in_group: bool  # True — вещь в группе, items заполнен; False — вещь не в группе, связей нет
  group_id: Optional[int] = None  # ID группы (если in_group)
  group_name: Optional[str] = None  # Название группы (если in_group)
  items: List[FeedItemResponse] = []  # Карточки всех вещей группы (включая запрошенную), иначе пусто


class ItemActionRequest(BaseModel):
  """Запрос на действие с товаром"""
  action: str  # "like", "dislike", "save", "add_to_cart"
  quantity: Optional[int] = 1  # Для добавления в корзину

