import React, { createContext, useContext, useState, useCallback, useEffect, useLayoutEffect } from 'react';
import { fetchWithAuthRelogin, setSessionReloginHandler } from '../utils/sessionRelogin';
import {
  fetchGuestHtmlText,
  getUsersApiBase,
  responseIsMiniappAdminOnly,
} from '../utils/miniappAdminOnly';
import {
  hydrateAccessTokenFromStorage,
  getMiniappAccessToken,
  setMiniappAccessToken,
  clearMiniappAccessToken,
  getAuthChannel,
} from '../utils/miniappAccessToken';
import {
  fetchBrowserSessionRefresh,
  logoutBrowserSession,
  readMiniappBrowserCsrfCookie,
  setMiniappBrowserCsrfToken,
  clearMiniappBrowserCsrfToken,
} from '../utils/browserAuth';
import { hasTelegramWebAppInitData } from '../utils/telegramEnvironment';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => {
    hydrateAccessTokenFromStorage();
    const t = getMiniappAccessToken();
    return t;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [guestHtml, setGuestHtml] = useState(null);

  const login = useCallback(async (initData) => {
    if (!initData) {
      setError('Нет данных авторизации');
      setLoading(false);
      return false;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getUsersApiBase()}/auth/miniapp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (responseIsMiniappAdminOnly(res.status, data)) {
          const html = await fetchGuestHtmlText();
          setGuestHtml(html);
          setToken(null);
          setUser(null);
          clearMiniappAccessToken();
          setError(null);
          setLoading(false);
          return false;
        }
        const msg =
          typeof data.detail === 'string'
            ? data.detail
            : data.detail?.message || `Ошибка ${res.status}`;
        throw new Error(msg);
      }
      const data = await res.json();
      const t = data.access_token;
      setGuestHtml(null);
      clearMiniappBrowserCsrfToken();
      setMiniappAccessToken(t, 'telegram');
      setToken(t);
      const userRes = await fetch(`${getUsersApiBase()}/users/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (userRes.ok) {
        const userData = await userRes.json();
        setUser(userData);
      } else {
        const failBody = await userRes.json().catch(() => ({}));
        if (responseIsMiniappAdminOnly(userRes.status, failBody)) {
          const html = await fetchGuestHtmlText();
          setGuestHtml(html);
          setToken(null);
          setUser(null);
          clearMiniappAccessToken();
          setLoading(false);
          return false;
        }
        setUser({ id: data.user_id, privacy_policy_accepted: false });
      }
      return true;
    } catch (e) {
      setError(e.message);
      setToken(null);
      setUser(null);
      clearMiniappAccessToken();
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const ingestBrowserSession = useCallback(async (data) => {
    if (!data?.access_token) return;
    setLoading(true);
    setError(null);
    setGuestHtml(null);
    setMiniappAccessToken(data.access_token, 'browser');
    setToken(data.access_token);
    if (data.csrf_token) setMiniappBrowserCsrfToken(data.csrf_token);
    try {
      const userRes = await fetch(`${getUsersApiBase()}/users/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
        credentials: 'include',
      });
      if (userRes.ok) {
        const userData = await userRes.json();
        setUser(userData);
      } else {
        const failBody = await userRes.json().catch(() => ({}));
        if (responseIsMiniappAdminOnly(userRes.status, failBody)) {
          const html = await fetchGuestHtmlText();
          setGuestHtml(html);
          setToken(null);
          setUser(null);
          clearMiniappAccessToken();
          clearMiniappBrowserCsrfToken();
          return;
        }
        setUser({ id: data.user_id, privacy_policy_accepted: false });
      }
    } catch {
      setUser({ id: data.user_id, privacy_policy_accepted: false });
    } finally {
      setLoading(false);
    }
  }, []);

  const updateFromProfileResponse = useCallback((data) => {
    if (!data || typeof data !== 'object') return;
    if (data.access_token) {
      const ch = getAuthChannel();
      setMiniappAccessToken(data.access_token, ch);
      setToken(data.access_token);
    }
    const { access_token: _discard, ...userRest } = data;
    setUser(userRest);
  }, []);

  useLayoutEffect(() => {
    setSessionReloginHandler(async () => {
      if (hasTelegramWebAppInitData()) {
        return login(window.Telegram.WebApp.initData);
      }
      const refreshed = await fetchBrowserSessionRefresh();
      if (!refreshed?.access_token) return false;
      if (refreshed.csrf_token) setMiniappBrowserCsrfToken(refreshed.csrf_token);
      setMiniappAccessToken(refreshed.access_token, 'browser');
      setToken(refreshed.access_token);
      setGuestHtml(null);
      return true;
    });
    return () => setSessionReloginHandler(null);
  }, [login]);

  const acceptPolicy = useCallback(async () => {
    const t = token || getMiniappAccessToken();
    if (!t) return false;
    try {
      const res = await fetchWithAuthRelogin(`${getUsersApiBase()}/users/me`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${t}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ privacy_policy_accepted: true }),
      });
      if (!res.ok) return false;
      const userData = await res.json();
      updateFromProfileResponse(userData);
      return true;
    } catch {
      return false;
    }
  }, [token, updateFromProfileResponse]);

  const logout = useCallback(async () => {
    if (getAuthChannel() === 'browser') {
      await logoutBrowserSession();
    }
    clearMiniappAccessToken();
    setToken(null);
    setUser(null);
    setGuestHtml(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const t = token || getMiniappAccessToken();
    if (!t) return false;
    try {
      const res = await fetchWithAuthRelogin(`${getUsersApiBase()}/users/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (!res.ok) return false;
      const userData = await res.json();
      setUser(userData);
      return true;
    } catch {
      return false;
    }
  }, [token]);

  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData;
    const currentTgId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id ?? null;
    const savedToken = getMiniappAccessToken();

    let cancelled = false;

    async function boot() {
      if (savedToken) {
        setToken(savedToken);
        try {
          const r = await fetchWithAuthRelogin(`${getUsersApiBase()}/users/me`, {
            headers: { Authorization: `Bearer ${savedToken}` },
          });
          if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            if (responseIsMiniappAdminOnly(r.status, body)) {
              if (initData && !cancelled) {
                setToken(null);
                setUser(null);
                clearMiniappAccessToken();
                const reloginOk = await login(initData);
                if (reloginOk) return;
              }
              if (cancelled) return;
              setToken(null);
              setUser(null);
              clearMiniappAccessToken();
              const html = await fetchGuestHtmlText();
              if (cancelled) return;
              setGuestHtml(html);
              setLoading(false);
              return;
            }
            if (cancelled) return;
            setToken(null);
            setUser(null);
            clearMiniappAccessToken();
            if (initData) {
              await login(initData);
            } else {
              const csrf = readMiniappBrowserCsrfCookie();
              if (csrf) {
                const data = await fetchBrowserSessionRefresh();
                if (!cancelled && data?.access_token) {
                  await ingestBrowserSession(data);
                  return;
                }
              }
              setLoading(false);
            }
            return;
          }
          const userData = await r.json();
          if (cancelled) return;
          if (
            currentTgId != null &&
            userData.tgid != null &&
            Number(userData.tgid) !== Number(currentTgId)
          ) {
            setToken(null);
            setUser(null);
            clearMiniappAccessToken();
            if (initData) {
              await login(initData);
            } else {
              setLoading(false);
            }
            return;
          }
          setGuestHtml(null);
          setUser(userData);
          setLoading(false);
        } catch {
          if (cancelled) return;
          setToken(null);
          setUser(null);
          clearMiniappAccessToken();
          if (initData) {
            await login(initData);
          } else {
            const csrf = readMiniappBrowserCsrfCookie();
            if (csrf) {
              const data = await fetchBrowserSessionRefresh();
              if (!cancelled && data?.access_token) {
                await ingestBrowserSession(data);
                return;
              }
            }
            setLoading(false);
          }
        }
      } else if (initData) {
        await login(initData);
      } else {
        const csrf = readMiniappBrowserCsrfCookie();
        if (csrf) {
          const data = await fetchBrowserSessionRefresh();
          if (!cancelled && data?.access_token) {
            await ingestBrowserSession(data);
            return;
          }
        }
        if (!cancelled) setLoading(false);
      }
    }

    boot();
    return () => {
      cancelled = true;
    };
  }, [login, ingestBrowserSession]);

  useEffect(() => {
    if (!user || !token) return undefined;
    const base = getUsersApiBase();
    if (!base) return undefined;
    const ping = () => {
      const opts = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      };
      if (getAuthChannel() === 'browser') {
        opts.credentials = 'include';
      }
      fetchWithAuthRelogin(`${base}/users/me/online`, opts).catch(() => {});
    };
    ping();
    const id = setInterval(ping, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [user, token]);

  const value = {
    user,
    token,
    loading,
    error,
    guestHtml,
    setGuestHtml,
    login,
    ingestBrowserSession,
    acceptPolicy,
    logout,
    refreshUser,
    updateFromProfileResponse,
    isPolicyAccepted: user?.privacy_policy_accepted === true,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
