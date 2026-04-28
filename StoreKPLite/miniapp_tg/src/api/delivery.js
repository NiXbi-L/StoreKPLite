import { fetchWithAuthRelogin } from '../utils/sessionRelogin';
import { getMiniappAccessToken } from '../utils/miniappAccessToken';

/**
 * API сервиса доставки (delivery-service).
 * Базовый URL: origin + REACT_APP_DELIVERY_API_PATH или /api/delivery
 */
function getDeliveryBase() {
  if (typeof window === 'undefined') return '';
  const origin = window.location.origin;
  const path = process.env.REACT_APP_DELIVERY_API_PATH || '/api/delivery';
  return origin + path;
}

function getAuthHeaders() {
  if (typeof window === 'undefined') return {};
  const token = getMiniappAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/**
 * Список пресетов доставки пользователя.
 * @returns {Promise<Array>}
 */
export async function getUserDeliveryPresets() {
  const url = `${getDeliveryBase()}/user-delivery-data/list`;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    if (res.status === 401) return [];
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка загрузки адресов: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Создать/обновить пресет доставки пользователя.
 * @param {{ phone_number?: string|null, delivery_method_id?: number|null, address?: string|null, recipient_name?: string|null, postal_code?: string|null, city_code?: number|null, cdek_delivery_point_code?: string|null }} payload
 */
export async function saveUserDeliveryPreset(payload) {
  const url = `${getDeliveryBase()}/user-delivery-data`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка сохранения адреса: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Обновить пресет доставки по id (режим редактирования).
 * @param {number} presetId
 * @param {{ phone_number?: string|null, delivery_method_id?: number|null, address?: string|null, recipient_name?: string|null, postal_code?: string|null, city_code?: number|null, cdek_delivery_point_code?: string|null }} payload
 */
export async function updateUserDeliveryPreset(presetId, payload) {
  const url = `${getDeliveryBase()}/user-delivery-data/${presetId}`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const res = await fetchWithAuthRelogin(url, {
    method: 'PUT',
    headers,
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка сохранения адреса: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Сделать пресет основным способом доставки.
 * @param {number} presetId
 */
export async function setDefaultUserDeliveryPreset(presetId) {
  const url = `${getDeliveryBase()}/user-delivery-data/${presetId}/set-default`;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { method: 'PUT', headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Удалить пресет доставки по id.
 * @param {number} presetId — id пресета (из списка/редактирования).
 */
export async function deleteUserDeliveryPreset(presetId) {
  const url = `${getDeliveryBase()}/user-delivery-data/${presetId}`;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { method: 'DELETE', headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка удаления адреса: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Получить список способов доставки с обязательными полями.
 * @returns {Promise<Array<{id:number, code:string, name:string, required_fields:string[]}>}
 */
export async function getDeliveryMethods() {
  const url = `${getDeliveryBase()}/delivery-methods`;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка загрузки способов доставки: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Перерасчёт стоимости доставки для чекаута.
 * @param {{ weight_gram: number, length_cm: number, width_cm: number, height_cm: number }} parcel
 * @param {string} deliveryMethodCode — PICKUP_LOCAL | COURIER_LOCAL | CDEK | CDEK_MANUAL
 * @param {string|null} [toCity] — город/адрес для подсказки расчёта (для CDEK; для CDEK_MANUAL не обязателен)
 * @param {{ cdek_declared_value_rub?: number, cdek_add_insurance?: boolean }|null} [cdekExtras] — для CDEK: объявленная стоимость груза (сумма товаров); при CDEK_ADD_INSURANCE_TO_ORDERS=1 на сервере включается страховка в калькуляторе
 * @returns {Promise<{ delivery_cost_rub: number|null }>} — для CDEK_MANUAL всегда null (доставка не в сумму оплаты до согласования)
 */
export async function calculateDeliveryCost(parcel, deliveryMethodCode, toCity = null, cdekExtras = null) {
  const url = `${getDeliveryBase()}/calculate-cost`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  };
  const body = {
    parcel: parcel || { weight_gram: 1000, length_cm: 40, width_cm: 30, height_cm: 10 },
    delivery_method_code: deliveryMethodCode,
  };
  if (toCity != null && String(toCity).trim()) body.to_city = String(toCity).trim();
  if (cdekExtras && typeof cdekExtras === 'object') {
    if (cdekExtras.cdek_declared_value_rub != null && Number.isFinite(Number(cdekExtras.cdek_declared_value_rub))) {
      body.cdek_declared_value_rub = Number(cdekExtras.cdek_declared_value_rub);
    }
    if (cdekExtras.cdek_add_insurance === true) body.cdek_add_insurance = true;
  }
  const res = await fetchWithAuthRelogin(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка расчёта доставки: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Получить список наших локальных ПВЗ (Usсурийск и т.п.).
 * @returns {Promise<Array<{id:number, city:string, address:string, is_active:boolean}>>}
 */
export async function getLocalPickupPoints() {
  const url = `${getDeliveryBase()}/local-pickup-points`;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка загрузки ПВЗ: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}


/**
 * Получить список ПВЗ CDEK для карты/списка.
 * @param {{ city?: string, lat?: number, lon?: number, limit?: number }} params
 * @returns {Promise<Array<{code:string, name:string, address:string, city?:string, lat?:number, lon?:number}>>}
 */
export async function getCdekPickupPoints(params = {}) {
  const baseUrl = `${getDeliveryBase()}/pickup-points`;
  const search = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, String(value));
  });

  const url = search.toString() ? `${baseUrl}?${search.toString()}` : baseUrl;
  const headers = getAuthHeaders();
  const res = await fetchWithAuthRelogin(url, { headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Ошибка загрузки ПВЗ CDEK: ${res.status}`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return res.json();
}



