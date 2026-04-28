import { isTelegramWebAppEnvironment } from './telegramEnvironment';
import { getAuthChannel, getMiniappAccessToken } from './miniappAccessToken';

/**
 * Скачивание файла в Telegram Mini App через нативный диалог (Bot API 8.0+).
 * Обычный <a download> во встроенном WebView часто не работает — клиент сам качает по HTTPS.
 *
 * @see https://core.telegram.org/bots/webapps — downloadFile, DownloadFileParams
 * На сервере для ответа желательны: Content-Disposition: attachment; filename="..."
 * и для веб-версии TG — Access-Control-Allow-Origin (см. настройки nginx для статики/API).
 *
 * @param {string} url — полный HTTPS URL файла
 * @param {string} fileName — имя файла для сохранения
 * @returns {boolean} true если вызван Telegram API (старый клиент — false, нужен fallback)
 */
export function tryTelegramDownloadFile(url, fileName) {
  if (typeof window === 'undefined' || !isTelegramWebAppEnvironment()) return false;
  const tg = window.Telegram?.WebApp;
  if (!tg || typeof tg.downloadFile !== 'function') {
    return false;
  }
  try {
    tg.downloadFile(
      {
        url,
        file_name: fileName || 'file.jpg',
      },
      () => {
        /* опционально: callback(accepted) — пользователь подтвердил или отменил */
      },
    );
    return true;
  } catch {
    return false;
  }
}

/** Fallback: открыть URL (браузер / старый Telegram) */
export function openDownloadUrlFallback(url) {
  if (typeof window === 'undefined') return;
  const tg = isTelegramWebAppEnvironment() ? window.Telegram?.WebApp : null;
  if (tg && typeof tg.openLink === 'function') {
    tg.openLink(url);
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

/**
 * Браузер / PWA / старый Telegram без downloadFile: тихая загрузка fetch → blob → <a download>.
 * Без новых вкладок и без Share — иначе на мобильных ломается страница / уводит в загрузчик.
 * Обычный fetch (не fetchWithAuthRelogin): при 401 не запускаем релогин, превью в галерее не отваливаются.
 *
 * @param {string} url — полный URL (желательно уже с ?access_token=)
 * @param {string} [fileName='image.jpg']
 * @returns {Promise<boolean>} удалось ли инициировать сохранение
 */
export async function downloadImageUrlInBrowser(url, fileName = 'image.jpg') {
  if (typeof window === 'undefined') return false;
  const name = (fileName && String(fileName).trim()) || 'image.jpg';
  const headers = {};
  // URL уже с ?access_token= из getTryOnDownloadUrl — не дублируем Bearer (редкие прокси/WebView ведут себя странно).
  if (!url.includes('access_token=')) {
    const t = getMiniappAccessToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  let res;
  try {
    res = await fetch(url, {
      method: 'GET',
      headers,
      mode: 'cors',
      credentials: getAuthChannel() === 'browser' ? 'include' : 'omit',
    });
  } catch {
    return false;
  }
  if (!res.ok) return false;
  let blob;
  try {
    blob = await res.blob();
  } catch {
    return false;
  }
  if (!blob || blob.size === 0) return false;

  const blobUrl = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = name;
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch {
    URL.revokeObjectURL(blobUrl);
    return false;
  }
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  return true;
}
