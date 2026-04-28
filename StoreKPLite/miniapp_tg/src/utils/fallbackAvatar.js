/**
 * Статические заглушки: miniapp_tg/public/static/fallback_avatars/
 * После добавления файлов: python scripts/compress_fallback_avatars.py
 * и синхронизируйте список с manifest.json.
 */
export const FALLBACK_AVATAR_FILES = ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg'];

const BASE_PATH = '/static/fallback_avatars';

function publicUrl(path) {
  const prefix = typeof process !== 'undefined' && process.env.PUBLIC_URL ? process.env.PUBLIC_URL : '';
  return `${prefix}${path}`;
}

const ANON_SESSION_KEY = 'mw_fallback_avatar_seed';

function stableAnonSeed() {
  try {
    let v = sessionStorage.getItem(ANON_SESSION_KEY);
    if (!v) {
      v = String((Math.random() * 0xffffffff) >>> 0);
      sessionStorage.setItem(ANON_SESSION_KEY, v);
    }
    return v;
  } catch {
    return 'anon';
  }
}

/**
 * Детерминированный выбор по seed (например user_id); без seed — один вариант на сессию вкладки.
 */
export function fallbackAvatarUrl(seed) {
  const effective = seed != null && seed !== '' ? String(seed) : stableAnonSeed();
  let n = 0;
  for (let i = 0; i < effective.length; i += 1) {
    n = (Math.imul(31, n) + effective.charCodeAt(i)) >>> 0;
  }
  const idx = n % FALLBACK_AVATAR_FILES.length;
  return publicUrl(`${BASE_PATH}/${FALLBACK_AVATAR_FILES[idx]}`);
}
