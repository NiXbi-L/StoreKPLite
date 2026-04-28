import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { fetchGuestHtmlText } from '../../utils/miniappAdminOnly';
import { telegramBrowserLoginLaunchUrl, isLikelyMobileBrowser } from '../../utils/telegramBrowserDeepLink';
import { browserLoginStart, browserLoginComplete } from './browserLoginApi';
import { startBrowserLoginPolling } from './browserLoginPolling';

/** Официальная монохромная маска логотипа Telegram (simple-icons), viewBox 24×24 */
function TelegramLogoIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="44"
      height="44"
      aria-hidden
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"
      />
    </svg>
  );
}

export function TelegramBrowserLoginPanel() {
  const navigate = useNavigate();
  const { ingestBrowserSession, guestHtml, setGuestHtml } = useAuth();
  const [deepLink, setDeepLink] = useState('');
  const [code, setCode] = useState('');
  const [expiresInSec, setExpiresInSec] = useState(300);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [popupBlocked, setPopupBlocked] = useState(false);
  const openedLinkRef = useRef('');
  const isMobile = useMemo(() => isLikelyMobileBrowser(), []);

  const startFlow = useCallback(async () => {
    setError(null);
    setPopupBlocked(false);
    setBusy(true);
    setDeepLink('');
    setCode('');
    openedLinkRef.current = '';
    try {
      const d = await browserLoginStart();
      setCode(d.code);
      setDeepLink(d.deep_link);
      setExpiresInSec(d.expires_in);
    } catch (e) {
      setError(e.message || 'Не удалось начать вход');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!code) return undefined;
    const stop = startBrowserLoginPolling(code, {
      onReady: async (c) => {
        try {
          const r = await browserLoginComplete(c, { setGuestHtml });
          if (r.adminOnly) return;
          await ingestBrowserSession(r.data);
          navigate('/', { replace: true });
        } catch (err) {
          setError(err.message || 'Ошибка входа');
        }
      },
      onForbidden: async () => {
        const html = await fetchGuestHtmlText();
        setGuestHtml(html);
      },
      onError: (err) => {
        setError(err.message || 'Ошибка проверки статуса');
      },
    });
    return stop;
  }, [code, ingestBrowserSession, navigate, setGuestHtml]);

  useEffect(() => {
    if (!deepLink || !isMobile || openedLinkRef.current === deepLink) return;
    openedLinkRef.current = deepLink;
    const launchUrl = telegramBrowserLoginLaunchUrl(deepLink);
    const w = window.open(launchUrl, '_blank', 'noopener,noreferrer');
    if (!w || w.closed) {
      setPopupBlocked(true);
    }
  }, [deepLink, isMobile]);

  if (guestHtml != null) {
    return null;
  }

  const waiting = Boolean(code);

  return (
    <div className="browser-login-card browser-login-card--telegram">
      <div className="browser-login-card__row">
        <div className="browser-login-card__tg-mark">
          <TelegramLogoIcon className="browser-login-card__tg-logo" />
        </div>
        {!waiting ? (
          <button
            type="button"
            className="browser-login-card__tg-btn"
            onClick={() => void startFlow()}
            disabled={busy}
          >
            {busy ? (
              <span className="browser-login-card__tg-btn-inner">
                <span className="browser-login-card__spinner" aria-hidden />
                Подождите…
              </span>
            ) : (
              'Войти через Telegram'
            )}
          </button>
        ) : isMobile ? (
          popupBlocked && deepLink ? (
            <a
              className="browser-login-card__tg-btn browser-login-card__tg-btn--link"
              href={telegramBrowserLoginLaunchUrl(deepLink)}
              target="_blank"
              rel="noreferrer"
            >
              Открыть Telegram
            </a>
          ) : (
            <div className="browser-login-card__tg-wait">
              <span className="browser-login-card__spinner browser-login-card__spinner--inline" aria-hidden />
              Ожидаем в боте…
            </div>
          )
        ) : (
          <span className="browser-login-card__desktop-prompt">Как открыть бота</span>
        )}
      </div>

      {waiting && !isMobile && (
        <>
          <div className="browser-login-card__desktop-actions">
            <button
              type="button"
              className="browser-login-card__desktop-btn browser-login-card__desktop-btn--primary"
              onClick={() => window.open(deepLink, '_blank', 'noopener,noreferrer')}
            >
              Открыть ссылку
            </button>
            <button
              type="button"
              className="browser-login-card__desktop-btn browser-login-card__desktop-btn--secondary"
              onClick={() =>
                navigate('/browser-login/qr', {
                  state: {
                    code,
                    deepLink,
                    expiresAt: Date.now() + expiresInSec * 1000,
                  },
                })
              }
            >
              Сканировать QR-код
            </button>
          </div>
          <p className="browser-login-card__desktop-hint">
            Ссылка и код действуют ограниченное время. Не передавайте их другим людям.
          </p>
        </>
      )}

      {error && <p className="browser-login-card__error">{error}</p>}
    </div>
  );
}
