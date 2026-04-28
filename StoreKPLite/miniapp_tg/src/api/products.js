import { fetchWithAuthRelogin } from '../utils/sessionRelogin';
import { getMiniappAccessToken } from '../utils/miniappAccessToken';
import {
  orderCheckoutPausePlainErrorText,
  responseIsCheckoutDisabled,
} from '../constants/checkoutPauseNotice';

function throwIfCheckoutDisabledResponse(res, data) {
  if (!responseIsCheckoutDisabled(res.status, data)) return;
  const err = new Error(orderCheckoutPausePlainErrorText());
  err.status = 403;
  err.checkoutDisabled = true;
  throw err;
}

/**
 * API каталога товаров (products service).
 * Базовый URL: origin + REACT_APP_PRODUCTS_API_PATH или /api/products
 */
function getProductsBase() {
  if (typeof window === 'undefined') return '';
  const origin = window.location.origin;
  const path = process.env.REACT_APP_PRODUCTS_API_PATH || '/api/products';
  return origin + path;
}

function getAuthHeaders() {
  if (typeof window === 'undefined') return {};
  const token = getMiniappAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/** Заголовок платформы для кеша лайков и bump ревизий на бэке. */
function miniappPlatformHeaders() {
  return { 'X-Platform': 'tg' };
}

const CATALOG_PAGE_SIZE = 20;

const CHECKOUT_PROMO_STORAGE_KEY = 'matchwear_checkout_promo_code';

/** Промокод для чекаута (сохраняется между экраном товара и оформлением). */
export function getStoredCheckoutPromo() {
  try {
    return localStorage.getItem(CHECKOUT_PROMO_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function setStoredCheckoutPromo(code) {
  try {
    const t = String(code || '').trim();
    if (t) localStorage.setItem(CHECKOUT_PROMO_STORAGE_KEY, t);
    else localStorage.removeItem(CHECKOUT_PROMO_STORAGE_KEY);
  } catch (_) {
    /* ignore */
  }
}

/**
 * Запросить одну страницу каталога.
 * @param {number} offset - смещение
 * @param {number} [limit=20] - размер страницы
 * @param {string} [q] - поисковый запрос
 * @param {Array<number>|null} [itemTypeIds] - фильтр по типам товара (несколько)
 * @param {number|null} [priceMin] - минимальная цена (руб)
 * @param {number|null} [priceMax] - максимальная цена (руб)
 * @param {boolean|null} [isLegit] - фильтр по типу: оригинал (true) или реплика (false)
 * @returns {Promise<{ items: Array, total: number, has_more: boolean, next_offset: number|null }>}
 */
export async function fetchCatalogPage(offset = 0, limit = CATALOG_PAGE_SIZE, q, itemTypeIds, priceMin, priceMax, isLegit) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  if (q && q.trim()) {
    params.set('q', q.trim());
  }
  if (Array.isArray(itemTypeIds) && itemTypeIds.length) {
    itemTypeIds.forEach((id) => {
      if (id != null && id !== '') {
        params.append('item_type_id', String(id));
      }
    });
  }
  if (priceMin != null && priceMin !== '') {
    params.set('price_min', String(Number(priceMin)));
  }
  if (priceMax != null && priceMax !== '') {
    params.set('price_max', String(Number(priceMax)));
  }
  if (isLegit !== null && isLegit !== undefined) {
    params.set('is_legit', String(isLegit));
  }
  const url = `${getProductsBase()}/feed/catalog?${params.toString()}`;
  const authHeaders = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, Object.keys(authHeaders).length ? { headers: authHeaders } : undefined);
  if (!res.ok) {
    const err = new Error(res.status === 404 ? 'Нет товаров' : `Ошибка загрузки: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Карточки для ленты (свайпы). Стабильный порядок, без фильтров и без перемешивания.
 * @param {number} offset - смещение
 * @param {number} [limit=20] - размер страницы
 * @returns {Promise<{ items: Array, total: number, has_more: boolean, next_offset: number|null }>}
 */
/**
 * Сводка по полке лайков: число и ревизия. Передайте knownRev с прошлого ответа — при неизменных лайках бэк ответит из Redis без COUNT в БД.
 * @param {'like'|'dislike'|'save'} [action='like']
 * @param {number|null} [knownRev]
 * @returns {Promise<{ total: number, rev: number }>}
 */
export async function fetchLikedSummary(action = 'like', knownRev = null) {
  const params = new URLSearchParams();
  params.set('action', action);
  if (knownRev != null && knownRev !== '') {
    params.set('known_rev', String(Number(knownRev)));
  }
  const headers = { ...getAuthHeaders(), ...miniappPlatformHeaders() };
  const url = `${getProductsBase()}/likes/summary?${params.toString()}`;
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    if (res.status === 401) return { total: 0, rev: 0 };
    const err = new Error(`Ошибка загрузки: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Понравившиеся пачками (как каталог).
 * @param {number} offset
 * @param {number} [limit=20]
 * @param {Object} [filters]
 * @returns {Promise<{ items: Array, total: number, has_more: boolean, next_offset: number|null }>}
 */
export async function fetchLikedPage(offset = 0, limit = CATALOG_PAGE_SIZE, filters = {}) {
  const params = new URLSearchParams();
  params.set('action', 'like');
  params.set('offset', String(offset));
  params.set('limit', String(limit));
  if (filters.q && String(filters.q).trim()) {
    params.set('q', String(filters.q).trim());
  }
  if (Array.isArray(filters.itemTypeIds) && filters.itemTypeIds.length) {
    filters.itemTypeIds.forEach((id) => params.append('item_type_id', String(id)));
  }
  if (filters.priceMin != null && filters.priceMin !== '') {
    params.set('price_min', String(Number(filters.priceMin)));
  }
  if (filters.priceMax != null && filters.priceMax !== '') {
    params.set('price_max', String(Number(filters.priceMax)));
  }
  if (filters.isLegit !== null && filters.isLegit !== undefined) {
    params.set('is_legit', String(filters.isLegit));
  }
  const headers = { ...getAuthHeaders(), ...miniappPlatformHeaders() };
  const url = `${getProductsBase()}/likes/page?${params.toString()}`;
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    if (res.status === 401) {
      return { items: [], total: 0, has_more: false, next_offset: null };
    }
    const err = new Error(`Ошибка загрузки: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Полный список (устарело для мини-аппа; используйте fetchLikedPage). Оставлено для совместимости.
 * @returns {Promise<Array>}
 */
export async function fetchLikedItems(filters = {}) {
  const data = await fetchLikedPage(0, 10000, filters);
  return Array.isArray(data.items) ? data.items : [];
}

/**
 * Список типов товаров для фильтра.
 * @returns {Promise<Array<{ id: number, name: string }>>}
 */
export async function fetchItemTypes() {
  const url = `${getProductsBase()}/item-types`;
  const res = await fetchWithAuthRelogin(url);
  if (!res.ok) {
    const err = new Error(`Ошибка загрузки типов: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Детальная информация о товаре по ID.
 * Возвращает тот же формат, что и элементы ленты (FeedItemResponse).
 * @param {number|string} itemId
 */
export async function fetchItemById(itemId) {
  if (!itemId && itemId !== 0) {
    throw new Error('itemId обязателен');
  }
  const url = `${getProductsBase()}/items/${itemId}`;
  const authHeaders = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, Object.keys(authHeaders).length ? { headers: authHeaders } : undefined);
  if (!res.ok) {
    const err = new Error(res.status === 404 ? 'Товар не найден' : `Ошибка загрузки товара: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Очередь предзаказов: заказы со статусом «Выкуп», где в составе есть этот товар.
 * Снимок: без options.wait. Long poll: wait=true и revision из прошлого ответа.
 * @param {number|string} itemId
 * @param {{ wait?: boolean, revision?: string|null, signal?: AbortSignal }} [options]
 * @returns {Promise<{ count: number, first_buyout_at: string|null, application_deadline_at: string|null, global_buyout_count: number, wave_first_buyout_at: string|null, revision: string }>}
 */
export async function fetchItemBuyoutQueue(itemId, options = {}) {
  if (!itemId && itemId !== 0) {
    throw new Error('itemId обязателен');
  }
  const { wait = false, revision = null, signal } = options;
  const params = new URLSearchParams();
  if (wait) {
    params.set('wait', 'true');
    if (revision != null && revision !== '') {
      params.set('revision', revision);
    }
  }
  const qs = params.toString();
  const url = `${getProductsBase()}/items/${itemId}/buyout-queue${qs ? `?${qs}` : ''}`;
  const headers = { ...miniappPlatformHeaders(), ...getAuthHeaders() };
  const res = await fetchWithAuthRelogin(url, { headers, signal });
  if (!res.ok) {
    const err = new Error(`Очередь выкупа: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Сводка по отзывам товара (средняя оценка и количество) для кнопки «Отзывы N».
 * @param {number|string} itemId
 * @returns {Promise<{ average_rating: number, total_count: number }>}
 */
export async function getItemReviewsSummary(itemId) {
  if (!itemId && itemId !== 0) return { average_rating: 0, total_count: 0 };
  const url = `${getProductsBase()}/items/${itemId}/reviews/summary`;
  const res = await fetchWithAuthRelogin(url);
  if (!res.ok) return { average_rating: 0, total_count: 0 };
  return res.json();
}

/**
 * Список отзывов товара с фильтрами.
 * @param {number|string} itemId
 * @param {{ sort?: 'date_asc'|'date_desc', stars?: number, limit?: number, offset?: number }} [params]
 * @returns {Promise<{ average_rating: number, total_count: number, reviews: Array }>}
 */
export async function getItemReviews(itemId, params = {}) {
  if (!itemId && itemId !== 0) return { average_rating: 0, total_count: 0, reviews: [] };
  const search = new URLSearchParams();
  if (params.sort) search.set('sort', params.sort);
  if (params.stars != null && params.stars >= 1 && params.stars <= 5) search.set('stars', String(params.stars));
  if (params.limit != null) search.set('limit', String(params.limit));
  if (params.offset != null) search.set('offset', String(params.offset));
  const url = `${getProductsBase()}/items/${itemId}/reviews?${search.toString()}`;
  const res = await fetchWithAuthRelogin(url);
  if (!res.ok) {
    const err = new Error(`Ошибка загрузки отзывов: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Поставить/обновить действие с товаром (лайк/дизлайк/сохранить/просмотр).
 * @param {number} itemId
 * @param {"like"|"dislike"|"save"|"view"} action
 */
export async function performItemAction(itemId, action) {
  const url = `${getProductsBase()}/items/${itemId}/action`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
    ...miniappPlatformHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ action }),
  });
  if (!res.ok) {
    const err = new Error(`Ошибка действия с товаром: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Удалить действие с товаром (снять лайк/дизлайк/сохранение).
 * @param {number} itemId
 */
export async function removeItemAction(itemId) {
  const url = `${getProductsBase()}/items/${itemId}/action`;
  const headers = { ...getAuthHeaders(), ...miniappPlatformHeaders() };
  const res = await fetchWithAuthRelogin(url, {
    method: 'DELETE',
    headers: Object.keys(headers).length ? headers : undefined,
  });
  if (!res.ok && res.status !== 404) {
    const err = new Error(`Ошибка удаления действия с товаром: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.ok;
}

/**
 * Получить список позиций корзины с товарами и ценами.
 * @returns {Promise<Array<{ id: number, item: object, size: string|null, quantity: number, stock_type: string, price_rub: number }>>}
 */
export async function getCartItems() {
  const url = `${getProductsBase()}/cart/items`;
  const res = await fetchWithAuthRelogin(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    if (res.status === 401) return [];
    const err = new Error(`Ошибка загрузки корзины: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Габариты и вес сборной посылки по выбранным позициям корзины (для расчёта доставки).
 * @param {number[]} cartItemIds — id позиций корзины
 * @returns {Promise<{ weight_gram: number, length_cm: number, width_cm: number, height_cm: number }>}
 */
export async function getCartParcel(cartItemIds) {
  const url = `${getProductsBase()}/cart/parcel`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ cart_item_ids: cartItemIds || [] }),
  });
  if (!res.ok) {
    const err = new Error(`Ошибка расчёта посылки: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Удалить позицию из корзины по cart_item_id.
 * @param {number} cartItemId
 * @returns {Promise<boolean>}
 */
export async function deleteCartItem(cartItemId) {
  const url = `${getProductsBase()}/cart/items/${cartItemId}`;
  const res = await fetchWithAuthRelogin(url, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка удаления: ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return true;
}

/**
 * Добавить товар в корзину. stock_type (из наличия / под заказ) определяется на беке по выбранному размеру.
 * @param {number} itemId
 * @param {string|null} size — выбранный размер (если у товара есть размеры)
 * @param {number} [quantity=1]
 * @returns {Promise<{ success: boolean, stock_type?: string }>}
 */
export async function addToCart(itemId, size = null, quantity = 1) {
  const url = `${getProductsBase()}/cart/items`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      item_id: itemId,
      size: size && String(size).trim() ? String(size).trim() : null,
      quantity: Number(quantity) || 1,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка добавления в корзину: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Установить количество товара в корзине по item_id и размеру (абсолютное значение; 0 — удалить).
 * @param {number} itemId
 * @param {string|null} size
 * @param {number} quantity
 * @returns {Promise<{ success: boolean, quantity: number }>}
 */
export async function setCartQuantityByItem(itemId, size, quantity) {
  const url = `${getProductsBase()}/cart/items/by-item`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({
      item_id: itemId,
      size: size && String(size).trim() ? String(size).trim() : null,
      quantity: Math.max(0, Number(quantity) || 0),
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка обновления корзины: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Изменить размер позиции корзины по cart_item_id.
 * @param {number} cartItemId
 * @param {string|null} size
 * @returns {Promise<{ success: boolean }>}
 */
export async function updateCartItemSize(cartItemId, size) {
  const url = `${getProductsBase()}/cart/items/${cartItemId}/size`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({
      size: size && String(size).trim() ? String(size).trim() : null,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка смены размера: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Изменить тип заказа позиции корзины по cart_item_id.
 * @param {number} cartItemId
 * @param {"preorder"|"in_stock"} stockType
 * @returns {Promise<{ success: boolean, stock_type: string }>}
 */
export async function updateCartItemStockType(cartItemId, stockType) {
  const url = `${getProductsBase()}/cart/items/${cartItemId}/stock-type?stock_type=${encodeURIComponent(stockType)}`;
  const headers = {
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'PATCH',
    headers,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка смены типа заказа: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Получить список заказов пользователя.
 * @returns {Promise<Array<{ id: number, status: string, order_data: object, created_at: string, order_total?: number, ... }>>}
 */
export async function getOrders() {
  const url = `${getProductsBase()}/orders`;
  const res = await fetchWithAuthRelogin(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    const err = new Error(res.status === 401 ? 'Необходима авторизация' : `Ошибка загрузки заказов: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Получить заказ по ID (для страницы отзыва).
 * @param {number} orderId
 * @returns {Promise<{ id: number, status: string, order_data: { items: Array<{ item_id: number, name: string, ... }> }, ... }>}
 */
export async function getOrder(orderId) {
  const url = `${getProductsBase()}/orders/${orderId}`;
  const res = await fetchWithAuthRelogin(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    const err = new Error(res.status === 404 ? 'Заказ не найден' : `Ошибка загрузки заказа: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Оставить отзыв по товару из завершённого заказа. Фото сжимаются на клиенте перед вызовом.
 * @param {number} orderId
 * @param {{ item_id: number, rating: number, comment: string, photoBlobs?: Blob[] }} payload — photoBlobs уже сжатые (JPEG)
 */
export async function createOrderReview(orderId, payload) {
  const url = `${getProductsBase()}/orders/${orderId}/reviews`;
  const form = new FormData();
  form.append('item_id', String(payload.item_id));
  form.append('rating', String(payload.rating));
  form.append('comment', String(payload.comment ?? ''));
  const blobs = payload.photoBlobs || [];
  for (let i = 0; i < blobs.length; i++) {
    form.append('files', blobs[i], `photo_${i}.jpg`);
  }
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка отправки отзыва: ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}

/**
 * Скрыть заказ из списка (для статусов «отменен», «завершен»).
 * @param {number} orderId
 */
export async function hideOrder(orderId) {
  const url = `${getProductsBase()}/orders/${orderId}/hide`;
  const res = await fetchWithAuthRelogin(url, { method: 'POST', headers: getAuthHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка: ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}

/**
 * Отменить заказ (только для статусов «Ожидает», «Выкуп»).
 * @param {number} orderId
 */
export async function cancelOrder(orderId) {
  const url = `${getProductsBase()}/orders/${orderId}/cancel`;
  const res = await fetchWithAuthRelogin(url, { method: 'POST', headers: getAuthHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка: ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}

/**
 * Создать заказ из выбранных позиций корзины (чекаут). Товары со склада резервируются.
 * Данные выбранного способа доставки фиксируются в заказе для накладной.
 * @param {{ cart_item_ids: number[], delivery_preset_id?: number|null, recipient_name?: string|null, phone_number?: string|null, delivery_address?: string|null, delivery_postal_code?: string|null, delivery_city_code?: number|null, delivery_cost_rub?: number|null, delivery_method_code?: string|null, cdek_delivery_point_code?: string|null }} payload
 * @returns {Promise<{ order_id: number, order_total_rub: number }>}
 */
export async function checkoutCreateOrder(payload) {
  const url = `${getProductsBase()}/orders/checkout`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const body = {
    cart_item_ids: payload.cart_item_ids || [],
    recipient_name: payload.recipient_name ?? null,
    phone_number: payload.phone_number ?? null,
  };
  const presetId = payload.delivery_preset_id;
  if (presetId != null && Number.isFinite(Number(presetId))) {
    body.delivery_preset_id = Number(presetId);
  }
  if (payload.delivery_address != null) body.delivery_address = payload.delivery_address;
  if (payload.delivery_postal_code != null) body.delivery_postal_code = payload.delivery_postal_code;
  if (payload.delivery_city_code != null) body.delivery_city_code = payload.delivery_city_code;
  if (payload.delivery_cost_rub != null) body.delivery_cost_rub = payload.delivery_cost_rub;
  if (payload.delivery_method_code != null) body.delivery_method_code = payload.delivery_method_code;
  const pvz = payload.cdek_delivery_point_code != null ? String(payload.cdek_delivery_point_code).trim() : '';
  if (pvz) body.cdek_delivery_point_code = pvz;
  if (payload.promo_code != null && String(payload.promo_code).trim()) {
    body.promo_code = String(payload.promo_code).trim();
  }
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throwIfCheckoutDisabledResponse(res, data);
    const msg = data.detail || `Ошибка создания заказа: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Предпросмотр чекаута: суммы/скидки без создания заказа.
 * @param {{ cart_item_ids: number[], delivery_preset_id?: number|null, recipient_name?: string|null, phone_number?: string|null, delivery_address?: string|null, delivery_postal_code?: string|null, delivery_city_code?: number|null, delivery_cost_rub?: number|null, delivery_method_code?: string|null, cdek_delivery_point_code?: string|null }} payload
 * @returns {Promise<{ order_total_rub:number, delivery_cost_rub:number|null, payable_total_rub:number, promo_discount_rub?:number, owner_waiver?:boolean }>}
 */
export async function checkoutPreviewOrder(payload) {
  const url = `${getProductsBase()}/orders/checkout/preview`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const body = {
    cart_item_ids: payload.cart_item_ids || [],
    recipient_name: payload.recipient_name ?? null,
    phone_number: payload.phone_number ?? null,
  };
  const presetIdPreview = payload.delivery_preset_id;
  if (presetIdPreview != null && Number.isFinite(Number(presetIdPreview))) {
    body.delivery_preset_id = Number(presetIdPreview);
  }
  if (payload.delivery_address != null) body.delivery_address = payload.delivery_address;
  if (payload.delivery_postal_code != null) body.delivery_postal_code = payload.delivery_postal_code;
  if (payload.delivery_city_code != null) body.delivery_city_code = payload.delivery_city_code;
  if (payload.delivery_cost_rub != null) body.delivery_cost_rub = payload.delivery_cost_rub;
  if (payload.delivery_method_code != null) body.delivery_method_code = payload.delivery_method_code;
  const pvzPreview = payload.cdek_delivery_point_code != null ? String(payload.cdek_delivery_point_code).trim() : '';
  if (pvzPreview) body.cdek_delivery_point_code = pvzPreview;
  if (payload.promo_code != null && String(payload.promo_code).trim()) {
    body.promo_code = String(payload.promo_code).trim();
  }
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throwIfCheckoutDisabledResponse(res, data);
    const msg = data.detail || `Ошибка предпросмотра заказа: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Создать платёж по заказу, получить ссылку на оплату.
 * Сумма к оплате считается на беке (order_total + delivery из заказа).
 * @param {number} orderId
 * @param {string} returnUrl — URL возврата после оплаты (обратно в миниапп)
 * @returns {Promise<{ confirmation_url?: string|null, owner_payment_skipped?: boolean }>}
 */
export async function createOrderPayment(orderId, returnUrl) {
  const url = `${getProductsBase()}/orders/${orderId}/create-payment`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      return_url: String(returnUrl),
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка создания платежа: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/** Дашборд реферальных промокодов (привязка к текущему пользователю). */
export async function fetchReferralDashboard(historyMonths = 12) {
  const params = new URLSearchParams();
  if (historyMonths) params.set('history_months', String(historyMonths));
  const q = params.toString();
  const url = `${getProductsBase()}/referral/dashboard${q ? `?${q}` : ''}`;
  const res = await fetchWithAuthRelogin(url, {
    method: 'GET',
    headers: { ...getAuthHeaders() },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка загрузки: ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}
