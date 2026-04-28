function normalizeEnvOrigin(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  try {
    const u = new URL(/^https?:\/\//i.test(s) ? s : `https://${s}`);
    return `${u.protocol}//${u.host}`;
  } catch {
    return '';
  }
}

/**
 * Публичная ссылка для превью в мессенджерах (nginx → products-service, без /api/products).
 */
export function buildShareCatalogUrl(itemId) {
  const origin =
    normalizeEnvOrigin(process.env.REACT_APP_PUBLIC_ORIGIN) ||
    (typeof window !== 'undefined' ? window.location.origin : '');
  const prefix = (process.env.REACT_APP_SHARE_CATALOG_PATH || '/share/catalog').replace(/\/+$/, '');
  return `${origin}${prefix}/${itemId}`;
}

function isMobileUserAgent() {
  if (typeof navigator === 'undefined') return false;
  return /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || '');
}

/**
 * iOS/Android: системный share (если доступен). Иначе — копирование ссылки в буфер.
 * @returns {'shared'|'copied'}
 */
export async function runCatalogShare({ shareUrl, title }) {
  const label = (title && String(title).trim()) || 'MatchWear';
  const text = `${label} — MatchWear`;

  if (isMobileUserAgent() && typeof navigator !== 'undefined' && navigator.share) {
    try {
      await navigator.share({
        title: text,
        text,
        url: shareUrl,
      });
      return 'shared';
    } catch (e) {
      if (e && e.name === 'AbortError') {
        return 'shared';
      }
    }
  }

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(shareUrl);
    return 'copied';
  }

  throw new Error('Не удалось скопировать ссылку');
}
