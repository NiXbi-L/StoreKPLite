import { getUsersApiBase, fetchGuestHtmlText, responseIsMiniappAdminOnly } from '../../utils/miniappAdminOnly';

/**
 * @returns {Promise<{ code: string, deep_link: string, expires_in: number }>}
 */
export async function browserLoginStart() {
  const base = getUsersApiBase();
  const res = await fetch(`${base}/auth/browser-login/start`, { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      typeof data.detail === 'string'
        ? data.detail
        : data.detail?.message || `Ошибка ${res.status}`;
    throw new Error(msg);
  }
  return {
    code: data.code,
    deep_link: data.deep_link,
    expires_in: Number(data.expires_in) > 0 ? Number(data.expires_in) : 300,
  };
}

/**
 * Одноразовый обмен кода на сессию: повторный complete с тем же кодом вернёт ошибку (ключ удалён).
 * @param {string} code
 * @param {{ setGuestHtml?: (html: string) => void }} [opts]
 */
export async function browserLoginComplete(code, opts = {}) {
  const base = getUsersApiBase();
  const res = await fetch(`${base}/auth/browser-login/complete`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (responseIsMiniappAdminOnly(res.status, data) && typeof opts.setGuestHtml === 'function') {
      const html = await fetchGuestHtmlText();
      opts.setGuestHtml(html);
      return { ok: false, adminOnly: true, data };
    }
    const msg =
      typeof data.detail === 'string'
        ? data.detail
        : data.detail?.message || `Ошибка ${res.status}`;
    throw new Error(msg);
  }
  return { ok: true, adminOnly: false, data };
}
