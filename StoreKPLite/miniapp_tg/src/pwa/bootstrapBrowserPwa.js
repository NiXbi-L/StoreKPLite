/**
 * PWA только для браузерной версии (корень домена, путь /). Не трогаем Telegram WebView.
 * Путь /miniapp в URL — только для Mini App в Telegram (статика собирается с PUBLIC_URL=/miniapp), не отдельная «браузерная зона».
 * REACT_APP_PUBLIC_ORIGIN — публичный origin (без пути), напр. https://matchwear.ru. В docker-compose часто из API_BASE_URL.
 */

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

function publicPathSuffix() {
  const p = (process.env.PUBLIC_URL || '').replace(/\/$/, '');
  return p ? `${p}` : '';
}

function iconUrl(filename) {
  const prefix = publicPathSuffix();
  const path = `${prefix}/applogo/${filename}`.replace(/\/+/g, '/');
  const base = typeof window !== 'undefined' ? window.location.origin : '';
  const envOrigin = normalizeEnvOrigin(process.env.REACT_APP_PUBLIC_ORIGIN);
  const origin = envOrigin || base;
  if (!origin) return path;
  return new URL(path, origin).href;
}

export function applyWebAppManifest() {
  if (typeof document === 'undefined') return;
  if (document.querySelector('link[rel="manifest"]:not([data-pwa-injected="1"])')) return;
  if (document.querySelector('link[rel="manifest"][data-pwa-injected="1"]')) return;

  const envOrigin = normalizeEnvOrigin(process.env.REACT_APP_PUBLIC_ORIGIN);
  const base = envOrigin || (typeof window !== 'undefined' ? window.location.origin : '');
  const startUrl = `${base}/`;
  const scope = `${base}/`;

  const manifest = {
    id: startUrl,
    name: 'MatchWear',
    short_name: 'MatchWear',
    description: 'MatchWear — витрина и заказы',
    lang: 'ru',
    start_url: startUrl,
    scope,
    display: 'standalone',
    orientation: 'portrait-primary',
    background_color: '#fbfbf8',
    theme_color: '#fbfbf8',
    icons: [
      {
        src: iconUrl('Logo192.jpg'),
        sizes: '192x192',
        type: 'image/jpeg',
        purpose: 'any maskable',
      },
      {
        src: iconUrl('Logo512.jpg'),
        sizes: '512x512',
        type: 'image/jpeg',
        purpose: 'any maskable',
      },
    ],
  };

  const blob = new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('link');
  link.rel = 'manifest';
  link.href = url;
  link.setAttribute('data-pwa-injected', '1');
  document.head.appendChild(link);
}

export function applyAppleTouchIcon() {
  if (typeof document === 'undefined') return;

  /* До раннего return по apple-touch-icon: в index.html может уже стоять capable */
  if (!document.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
    const capable = document.createElement('meta');
    capable.name = 'apple-mobile-web-app-capable';
    capable.content = 'yes';
    capable.setAttribute('data-pwa-injected', '1');
    document.head.appendChild(capable);
  }

  if (document.querySelector('link[rel="apple-touch-icon"]:not([data-pwa-injected="1"])')) return;
  if (document.querySelector('link[rel="apple-touch-icon"][data-pwa-injected="1"]')) return;
  const link = document.createElement('link');
  link.rel = 'apple-touch-icon';
  link.href = iconUrl('Logo192.jpg');
  link.setAttribute('data-pwa-injected', '1');
  document.head.appendChild(link);
}

export function registerServiceWorker() {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return;
  if (process.env.NODE_ENV !== 'production') return;

  /*
   * public/sw.js → URL /sw.js. Регистрация как /miniapp/sw.js давала scope только /miniapp/, а браузерный
   * start_url в манифесте — корень / — вне scope. Для PWA с корня домена: /sw.js и scope "/".
   */
  const swPath = '/sw.js';

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(swPath, { scope: '/' })
      .catch(() => {
        /* тихо: иначе шум на не-HTTPS или если sw.js недоступен */
      });
  });
}

export function bootstrapBrowserPwa() {
  applyWebAppManifest();
  applyAppleTouchIcon();
  registerServiceWorker();
}
