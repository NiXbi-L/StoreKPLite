import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '../../contexts/AuthContext';
import { fetchGuestHtmlText } from '../../utils/miniappAdminOnly';
import { telegramBrowserLoginQrUrl } from '../../utils/telegramBrowserDeepLink';
import { browserLoginStart, browserLoginComplete } from './browserLoginApi';
import { startBrowserLoginPolling } from './browserLoginPolling';
import './BrowserLoginQrPage.css';

function formatMmSs(totalSec) {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

function BrowserLoginQrInner({ initial }) {
  const navigate = useNavigate();
  const { ingestBrowserSession, guestHtml, setGuestHtml } = useAuth();

  const [code, setCode] = useState(initial.code);
  const [deepLink, setDeepLink] = useState(initial.deepLink);
  const [expiresAt, setExpiresAt] = useState(initial.expiresAt);
  const [error, setError] = useState(null);
  const [regenFlash, setRegenFlash] = useState(false);
  const [tick, setTick] = useState(0);
  const [rotateInFlight, setRotateInFlight] = useState(false);

  const regenerate = useCallback(async () => {
    setRotateInFlight(true);
    setError(null);
    try {
      const d = await browserLoginStart();
      setCode(d.code);
      setDeepLink(d.deep_link);
      setExpiresAt(Date.now() + d.expires_in * 1000);
      setRegenFlash(true);
      setTimeout(() => setRegenFlash(false), 4000);
    } catch (e) {
      setError(e.message || 'Не удалось обновить QR');
    } finally {
      setRotateInFlight(false);
    }
  }, []);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!expiresAt) return undefined;
    const msLeft = expiresAt - Date.now();
    if (msLeft <= 0) {
      void regenerate();
      return undefined;
    }
    const t = setTimeout(() => void regenerate(), msLeft);
    return () => clearTimeout(t);
  }, [expiresAt, regenerate]);

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

  const secLeft = useMemo(
    () => Math.ceil((expiresAt - Date.now()) / 1000),
    [expiresAt, tick]
  );

  const qrOpenAppUrl = useMemo(() => telegramBrowserLoginQrUrl(deepLink), [deepLink]);

  if (guestHtml != null) {
    return (
      <div className="browser-login-qr-page browser-login-qr-page--restricted">
        <p>Сейчас доступ ограничен.</p>
      </div>
    );
  }

  return (
    <div className="browser-login-qr-page">
      <div className="browser-login-qr-page__shell">
        <button
          type="button"
          className="browser-login-qr-page__back"
          onClick={() => navigate('/browser-login', { replace: true })}
        >
          ← Назад
        </button>
        <h1 className="browser-login-qr-page__title">Вход через Telegram</h1>
        <p className="browser-login-qr-page__lead">
          Отсканируйте QR камерой телефона — откроется приложение Telegram; нажмите <strong>Start</strong> у бота.
        </p>

        {regenFlash && (
          <p className="browser-login-qr-page__flash" role="status">
            Код обновлён — используйте новый QR.
          </p>
        )}
        {error && <p className="browser-login-qr-page__error">{error}</p>}

        <div className="browser-login-qr-page__qr-wrap">
          <QRCodeSVG value={qrOpenAppUrl} size={220} level="M" includeMargin />
        </div>

        <p className="browser-login-qr-page__timer">
          Действует ещё: <strong>{formatMmSs(secLeft)}</strong>
          {rotateInFlight ? ' · обновление…' : null}
        </p>

        <p className="browser-login-qr-page__hint">
          Один код можно подтвердить только один раз. Не показывайте QR посторонним.
        </p>
      </div>
    </div>
  );
}

export default function BrowserLoginQrPage() {
  const location = useLocation();
  const st = location.state;
  if (!st?.code || !st?.deepLink || !st?.expiresAt) {
    return <Navigate to="/browser-login" replace />;
  }
  return <BrowserLoginQrInner initial={st} />;
}
