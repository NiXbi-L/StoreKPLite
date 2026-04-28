/**
 * Access JWT для миниаппа: в Telegram — дублируем в localStorage (как раньше),
 * в браузере — только в памяти; refresh живёт в httpOnly cookie на API.
 */

let memoryToken = null;
/** @type {'telegram' | 'browser'} */
let authChannel = 'telegram';

export function getAuthChannel() {
  return authChannel;
}

export function setAuthChannel(channel) {
  authChannel = channel === 'browser' ? 'browser' : 'telegram';
}

export function hydrateAccessTokenFromStorage() {
  try {
    memoryToken = localStorage.getItem('miniapp_token');
  } catch {
    memoryToken = null;
  }
}

/**
 * @param {string|null} token
 * @param {'telegram' | 'browser'} channel
 */
export function setMiniappAccessToken(token, channel = 'telegram') {
  setAuthChannel(channel);
  memoryToken = token || null;
  if (channel === 'browser') {
    try {
      localStorage.removeItem('miniapp_token');
    } catch {
      /* ignore */
    }
    return;
  }
  try {
    if (memoryToken) localStorage.setItem('miniapp_token', memoryToken);
    else localStorage.removeItem('miniapp_token');
  } catch {
    /* ignore */
  }
}

export function getMiniappAccessToken() {
  if (memoryToken) return memoryToken;
  if (authChannel === 'browser') return null;
  try {
    return localStorage.getItem('miniapp_token');
  } catch {
    return null;
  }
}

export function clearMiniappAccessToken() {
  memoryToken = null;
  authChannel = 'telegram';
  try {
    localStorage.removeItem('miniapp_token');
  } catch {
    /* ignore */
  }
}
