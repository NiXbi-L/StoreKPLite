/**
 * При истечении JWT (401) повторяем вход через Telegram initData или refresh cookie (браузер).
 * Регистрируется из AuthProvider (useLayoutEffect), чтобы дочерние API успели получить handler.
 */

import { getMiniappAccessToken, getAuthChannel } from './miniappAccessToken';
import { readMiniappBrowserCsrfCookie } from './browserAuth';

let reloginHandler = null;
/** @type {Promise<boolean>|null} */
let reloginInFlight = null;

export function setSessionReloginHandler(fn) {
  reloginHandler = typeof fn === 'function' ? fn : null;
}

function normalizeHeaders(h) {
  if (!h) return {};
  if (typeof Headers !== 'undefined' && h instanceof Headers) {
    const o = {};
    h.forEach((v, k) => {
      o[k] = v;
    });
    return o;
  }
  return { ...h };
}

function hadAuthIntent(headers) {
  if (getMiniappAccessToken()) return true;
  if (getAuthChannel() === 'browser' && readMiniappBrowserCsrfCookie()) return true;
  const o = normalizeHeaders(headers);
  return !!(o.Authorization || o.authorization);
}

/**
 * Один общий релогин на пачку параллельных 401.
 * @returns {Promise<boolean>}
 */
export async function tryReloginAfter401() {
  if (!reloginHandler) return false;
  if (reloginInFlight) return reloginInFlight;
  const p = (async () => {
    try {
      return await reloginHandler();
    } finally {
      reloginInFlight = null;
    }
  })();
  reloginInFlight = p;
  return p;
}

/**
 * Обёртка над fetch: при 401 и наличии сессии — login(initData), затем повтор с новым Bearer.
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function fetchWithAuthRelogin(url, options) {
  const opts = options ? { ...options } : {};
  if (getAuthChannel() === 'browser') {
    opts.credentials = opts.credentials || 'include';
  }
  const res = await fetch(url, opts);
  if (res.status !== 401) return res;
  if (!hadAuthIntent(opts.headers)) return res;
  const ok = await tryReloginAfter401();
  if (!ok) return res;
  const token = getMiniappAccessToken();
  if (!token) return res;
  const headersObj = normalizeHeaders(opts.headers);
  const nextHeaders = { ...headersObj, Authorization: `Bearer ${token}` };
  const retryOpts = { ...opts, headers: nextHeaders };
  if (getAuthChannel() === 'browser') {
    retryOpts.credentials = retryOpts.credentials || 'include';
  }
  return fetch(url, retryOpts);
}
