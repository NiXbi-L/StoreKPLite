/**
 * Браузерный вход: на мобилках открывать нативное приложение Telegram (tg://),
 * на десктопе оставлять https://t.me/... (вкладка / универсальная ссылка).
 * В QR всегда вшиваем tg:// — код сканирует телефон, ему нужна схема приложения.
 */

function httpsTmeToTgResolve(httpsDeepLink) {
  if (!httpsDeepLink || typeof httpsDeepLink !== 'string') return null;
  try {
    const u = new URL(httpsDeepLink);
    const host = u.hostname.toLowerCase();
    if (host !== 't.me' && host !== 'telegram.me') return null;
    const parts = u.pathname.replace(/^\//, '').split('/').filter(Boolean);
    const domain = parts[0];
    const start = u.searchParams.get('start');
    if (!domain || start == null || String(start).length === 0) return null;
    return `tg://resolve?domain=${encodeURIComponent(domain)}&start=${encodeURIComponent(start)}`;
  } catch {
    return null;
  }
}

/** Для QR: всегда tg://… при успешном разборе t.me, иначе исходная строка */
export function telegramBrowserLoginQrUrl(httpsDeepLink) {
  const tg = httpsTmeToTgResolve(httpsDeepLink);
  return tg ?? httpsDeepLink;
}

export function isLikelyMobileBrowser() {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  if (/Android|webOS|iPhone|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua)) {
    return true;
  }
  // iPadOS 13+ часто маскируется под Mac
  if (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) {
    return true;
  }
  return false;
}

/**
 * @param {string} httpsDeepLink — как с бэка, обычно https://t.me/bot?start=weblogin_...
 * @returns {string} на мобилке tg://resolve?domain=...&start=..., иначе исходная ссылка
 */
export function telegramBrowserLoginLaunchUrl(httpsDeepLink) {
  if (!httpsDeepLink || typeof httpsDeepLink !== 'string') return httpsDeepLink;
  if (!isLikelyMobileBrowser()) return httpsDeepLink;
  const tg = httpsTmeToTgResolve(httpsDeepLink);
  return tg ?? httpsDeepLink;
}
