/**
 * Контекст Telegram WebView vs обычный браузер.
 * В index.html SDK может грузиться по пути /miniapp/ без надёжного UA, но флаг ниже — только
 * tgWebAppData в URL или UA Telegram (см. __MINIAPP_IN_TELEGRAM_WEBVIEW__).
 */

export function isTelegramWebAppEnvironment() {
  if (typeof window === 'undefined') return false;
  if (typeof window.__MINIAPP_IN_TELEGRAM_WEBVIEW__ === 'boolean') {
    return window.__MINIAPP_IN_TELEGRAM_WEBVIEW__;
  }
  const loc = (window.location.search || '') + (window.location.hash || '');
  if (/tgWebAppData=/.test(loc)) return true;
  const ua = navigator.userAgent || '';
  return /Telegram/i.test(ua);
}

/** Подписанные initData от Telegram (реальный вход в миниапп, не пустой WebView). */
export function hasTelegramWebAppInitData() {
  if (typeof window === 'undefined') return false;
  const v = window.Telegram?.WebApp?.initData;
  return typeof v === 'string' && v.length > 0;
}
