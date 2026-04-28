import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { resetDocumentThemeOverrides } from './themeReset';
import { isTelegramWebAppEnvironment } from './utils/telegramEnvironment';
import { bootstrapBrowserPwa } from './pwa/bootstrapBrowserPwa';

/** Палитра только из index.css — сброс инлайн-темы Telegram при старте */
resetDocumentThemeOverrides();

if (typeof document !== 'undefined' && !isTelegramWebAppEnvironment()) {
  document.documentElement.classList.add('app-shell-browser');
  bootstrapBrowserPwa();
}

if (isTelegramWebAppEnvironment()) {
  try {
    window.Telegram?.WebApp?.ready();
  } catch (_) {
    /* ignore */
  }
}

const FONTS_READY_TIMEOUT_MS = 5000;

function AppWithResourceLoading() {
  const [resourcesReady, setResourcesReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const timeoutId = setTimeout(() => {
      if (!cancelled) setResourcesReady(true);
    }, FONTS_READY_TIMEOUT_MS);

    const whenReady =
      document.fonts && typeof document.fonts.ready !== 'undefined'
        ? document.fonts.ready
        : Promise.resolve();

    whenReady.then(() => {
      if (!cancelled) {
        clearTimeout(timeoutId);
        setResourcesReady(true);
      }
    });

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, []);

  if (!resourcesReady) {
    return (
      <div className="resources-loading" aria-live="polite" aria-busy="true">
        <div className="resources-loading__spinner" aria-hidden="true" />
        <p className="resources-loading__text">Загрузка…</p>
      </div>
    );
  }

  return <App />;
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <AppWithResourceLoading />
  </React.StrictMode>
);
