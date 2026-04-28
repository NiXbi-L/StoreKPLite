import { isTelegramWebAppEnvironment } from './telegramEnvironment';

/**
 * Редирект на оплату ЮKassa из Telegram Mini App.
 *
 * Внутри WebView Telegram User-Agent часто выглядит как «десктоп», из‑за этого на странице ЮKassa
 * для СБП / СберПэй / Т‑Пэй показывают QR вместо перехода в приложение банка.
 * Метод openLink открывает ссылку во внешнем браузере с нормальным mobile UA.
 *
 * @see https://core.telegram.org/bots/webapps
 */
export function openYookassaConfirmationUrl(url) {
  if (!url || typeof window === 'undefined') return;
  const tg = isTelegramWebAppEnvironment() ? window.Telegram?.WebApp : null;
  if (typeof tg?.openLink === 'function') {
    try {
      tg.openLink(url, { try_instant_view: false });
      return;
    } catch {
      /* fallback ниже */
    }
  }
  window.location.assign(url);
}
