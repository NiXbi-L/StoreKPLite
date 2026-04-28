import { getUsersApiBase } from '../utils/miniappAdminOnly';
import { getMiniappAccessToken } from '../utils/miniappAccessToken';
import { fetchWithAuthRelogin } from '../utils/sessionRelogin';

/**
 * @returns {Promise<{ sessions: Array<{ sid: string, user_agent: string, ip: string, created_at: number, last_seen: number, is_current: boolean }> }>}
 */
export async function fetchBrowserSessions() {
  const base = getUsersApiBase();
  const t = getMiniappAccessToken();
  if (!t) return { sessions: [] };
  const res = await fetchWithAuthRelogin(`${base}/auth/browser-login/sessions`, {
    headers: { Authorization: `Bearer ${t}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg =
      typeof err.detail === 'string' ? err.detail : err.detail?.message || `Ошибка ${res.status}`;
    throw new Error(msg);
  }
  return res.json();
}

export async function revokeBrowserSession(sid) {
  const base = getUsersApiBase();
  const t = getMiniappAccessToken();
  if (!t) throw new Error('Нет авторизации');
  const res = await fetchWithAuthRelogin(
    `${base}/auth/browser-login/sessions/${encodeURIComponent(sid)}/revoke`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${t}` },
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg =
      typeof err.detail === 'string' ? err.detail : err.detail?.message || `Ошибка ${res.status}`;
    throw new Error(msg);
  }
}
