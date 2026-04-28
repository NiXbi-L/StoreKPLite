/**
 * Возвращает URL с принудительной схемой https (для избежания mixed content на HTTPS-страницах).
 * Относительные пути возвращаются без изменений.
 * @param {string} url
 * @returns {string}
 */
export function ensureHttps(url) {
  if (!url || typeof url !== 'string') return url;
  const t = url.trim();
  if (t.startsWith('http://')) return 'https://' + t.slice(7);
  return t;
}
