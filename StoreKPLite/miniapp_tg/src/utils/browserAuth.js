import { getUsersApiBase } from './miniappAdminOnly';

/** При запросах с другого origin (localhost → прод API) CSRF-cookie не видна в document.cookie — держим копию из ответа API. */
let memoryCsrf = null;

export function setMiniappBrowserCsrfToken(token) {
  memoryCsrf = (token && String(token).trim()) || null;
}

export function clearMiniappBrowserCsrfToken() {
  memoryCsrf = null;
}

export function readMiniappBrowserCsrfCookie() {
  if (memoryCsrf) return memoryCsrf;
  if (typeof document === 'undefined') return '';
  const m = document.cookie.match(/(?:^|; )miniapp_csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : '';
}

/**
 * @returns {Promise<{ access_token: string, csrf_token: string, user_id: number }|null>}
 */
export async function fetchBrowserSessionRefresh() {
  const csrf = readMiniappBrowserCsrfCookie();
  if (!csrf) return null;
  const base = getUsersApiBase();
  const res = await fetch(`${base}/auth/browser-login/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    body: JSON.stringify({}),
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (data?.csrf_token) setMiniappBrowserCsrfToken(data.csrf_token);
  return data;
}

export async function logoutBrowserSession() {
  const csrf = readMiniappBrowserCsrfCookie();
  const base = getUsersApiBase();
  try {
    await fetch(`${base}/auth/browser-login/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      },
      body: JSON.stringify({}),
    });
  } finally {
    clearMiniappBrowserCsrfToken();
  }
}
