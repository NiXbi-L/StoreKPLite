/**
 * Захват по ссылке t.me/bot?startapp=item_ID: в истории WebView нет «нормального» шага назад.
 * Храним корневой id и флаг «ушли в другой товар из приложения», чтобы не путать нативным Back
 * и показать кнопку «в каталог» только на первом экране после deep link.
 */

import { isTelegramWebAppEnvironment } from './telegramEnvironment';

const ROOT_KEY = 'mw_startapp_item_root_id';
const INVALID_KEY = 'mw_startapp_item_invalidated';

export function markStartappItemRoot(itemId) {
  try {
    sessionStorage.setItem(ROOT_KEY, String(itemId));
    sessionStorage.removeItem(INVALID_KEY);
  } catch (_) {
    /* WebView / private mode */
  }
}

export function clearStartappItemRoot() {
  try {
    sessionStorage.removeItem(ROOT_KEY);
    sessionStorage.removeItem(INVALID_KEY);
  } catch (_) {
    /* */
  }
}

/** Вызвать при переходе на другой товар из карточки (связка / рекомендации), чтобы включить нативный Back. */
export function invalidateStartappItemRoot() {
  try {
    sessionStorage.setItem(INVALID_KEY, '1');
  } catch (_) {
    /* */
  }
}

export function shouldShowStartappHomeForItem(itemId) {
  if (itemId == null || itemId === '') return false;
  try {
    const root = sessionStorage.getItem(ROOT_KEY);
    const invalidated = sessionStorage.getItem(INVALID_KEY);
    return root === String(itemId) && invalidated !== '1';
  } catch (_) {
    return false;
  }
}

/**
 * Если пользователь открыл миниапп по startapp=item_ID и попал на карточку без state из каталога/ленты,
 * а initData пришёл с задержкой — помечаем корень здесь (не затираем при переходах с item в state).
 */
export function syncStartappRootFromTelegramForItem(itemId, blockInAppNav) {
  if (blockInAppNav || itemId == null || itemId === '' || !isTelegramWebAppEnvironment()) return;
  try {
    const sp = window.Telegram?.WebApp?.initDataUnsafe?.start_param || '';
    const m = /^item_(\d+)$/.exec(sp);
    if (m && m[1] === String(itemId)) {
      markStartappItemRoot(itemId);
    }
  } catch (_) {
    /* */
  }
}
