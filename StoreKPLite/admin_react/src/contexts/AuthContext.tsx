import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';
import apiClient, {
  clearAdminSession,
  setAdminCsrfToken,
  getCookie,
} from '../utils/apiClient';
import { persistAdminSessionFromApi, clearAdminPermissionCache } from '../utils/permissions';
import { encodeAdminLoginCredentials } from '../utils/sensitiveTransport';

interface AuthContextType {
  isAuthenticated: boolean;
  login: (login: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const refreshRes = await apiClient.post(
          '/users/admin/refresh',
          new URLSearchParams(),
          {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          },
        );
        if (refreshRes.status === 200 && refreshRes.data?.user_id != null) {
          const csrf = getCookie('admin_csrf_token');
          if (csrf) {
            setAdminCsrfToken(csrf);
          }
        }
        const response = await apiClient.get('/users/admin/me');
        if (response.status === 200) {
          persistAdminSessionFromApi(response.data);
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
        }
      } catch (error) {
        if (axios.isAxiosError(error)) {
          setIsAuthenticated(false);
        } else {
          setIsAuthenticated(false);
        }
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (loginValue: string, password: string) => {
    const loginFailedMessage =
      'Не удалось войти. Проверьте данные и попробуйте снова.';
    const sessionFailedMessage =
      'Сессия не установлена: cookie авторизации не доходят до API (разные домены у SPA и /api, блокировка cookie или настройки SameSite/HTTPS). Откройте админку через тот же origin, что и API.';

    try {
      const body = new URLSearchParams();
      body.set('credentials', encodeAdminLoginCredentials(loginValue, password));
      const response = await apiClient.post('/users/admin/login', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      if (response.status !== 200) {
        throw new Error(loginFailedMessage);
      }

      const csrf = getCookie('admin_csrf_token');
      if (csrf) setAdminCsrfToken(csrf);

      // Токены только в httpOnly cookie — успех входа подтверждаем запросом /me, а не полем access_token в JSON.
      let me;
      try {
        me = await apiClient.get('/users/admin/me');
      } catch (e) {
        if (axios.isAxiosError(e) && (e.response?.status === 401 || e.response?.status === 403)) {
          throw new Error(sessionFailedMessage);
        }
        throw e;
      }

      if (me.status !== 200 || me.data?.user_id == null) {
        throw new Error(sessionFailedMessage);
      }

      localStorage.setItem('admin_user_id', String(me.data.user_id));
      localStorage.setItem('admin_type', me.data.admin_type);
      persistAdminSessionFromApi(me.data);
      setIsAuthenticated(true);
    } catch (err) {
      if (err instanceof Error && err.message === sessionFailedMessage) {
        throw err;
      }
      throw new Error(loginFailedMessage);
    }
  };

  const logout = async () => {
    try {
      await apiClient.post('/users/admin/logout');
    } catch {
      // Даже если logout endpoint недоступен, локально завершаем сессию.
    }
    clearAdminSession();
    clearAdminPermissionCache();
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
