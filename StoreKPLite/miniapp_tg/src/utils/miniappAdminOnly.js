export function getUsersApiBase() {
  if (typeof window === 'undefined') return '';
  const abs = (process.env.REACT_APP_USERS_API_BASE || '').trim().replace(/\/+$/, '');
  if (abs) return abs;
  const origin = window.location.origin;
  const path = process.env.REACT_APP_API_PATH || '/api/users';
  return origin + path;
}

/** База URL сервиса статистики (миниапп: POST событий). По умолчанию тот же origin + /api/stats */
export function getStatsApiBase() {
  if (typeof window === 'undefined') return '';
  const abs = (process.env.REACT_APP_STATS_API_BASE || '').trim().replace(/\/+$/, '');
  if (abs) return abs;
  const origin = window.location.origin;
  const path = (process.env.REACT_APP_STATS_API_PATH || '/api/stats').replace(/\/+$/, '') || '/api/stats';
  return origin + path;
}

export function responseIsMiniappAdminOnly(status, body) {
  if (status !== 403 || !body) return false;
  const d = body.detail;
  return Boolean(d && typeof d === 'object' && d.code === 'MINIAPP_ADMIN_ONLY');
}

export async function fetchGuestHtmlText() {
  const fallback =
    '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head><body style="font-family:system-ui;padding:2rem;text-align:center"><p>Временно недоступно</p></body></html>';
  try {
    const r = await fetch(`${getUsersApiBase()}/public/miniapp-guest-html`);
    if (!r.ok) return fallback;
    const t = await r.text();
    return t && t.trim() ? t : fallback;
  } catch {
    return fallback;
  }
}
