/**
 * Временная пауза приёма заказов / оплаты (ЮKassa, переход на ИП).
 * Включить паузу в UI: true + на products-service ORDER_CHECKOUT_DISABLED=1 (или не задавать — по умолчанию блок).
 */
export const ORDER_CHECKOUT_PAUSE_TG_URL = 'https://t.me/MatchWear_chine';

/** Сообщение о паузе только на экране оформления заказа (CheckoutPage). Не берётся из .env — только пересборка миниаппа. */
export const SHOW_ORDER_CHECKOUT_PAUSE_BANNER = false;

export function orderCheckoutPauseBannerTextBeforeLink() {
  return 'Платежи временно не принимаются, оформление заказа недоступно. Подробности в нашем канале:';
}

/** Текст для ошибки API (403) и алертов */
export function orderCheckoutPausePlainErrorText() {
  return `${orderCheckoutPauseBannerTextBeforeLink()} ${ORDER_CHECKOUT_PAUSE_TG_URL}`;
}

/**
 * @param {number} status
 * @param {object} data - тело ответа JSON
 */
export function responseIsCheckoutDisabled(status, data) {
  if (status !== 403 || !data || typeof data !== 'object') return false;
  const d = data.detail;
  return typeof d === 'object' && d !== null && d.code === 'checkout_disabled';
}
