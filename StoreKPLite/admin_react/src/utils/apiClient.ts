import axios from 'axios';

// API URL для микросервисов (через nginx)
// Используем относительный путь - запросы идут на тот же домен/порт, откуда загружена страница
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

type RefreshResult = {
  /** Сессия продлена (новый access в httpOnly cookie); повторить запрос без Bearer. */
  renewed: boolean;
  definitiveFailure: boolean;
};

let refreshPromise: Promise<RefreshResult> | null = null;
let inMemoryCsrfToken: string | null = null;

export function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function csrfHeaders(): Record<string, string> {
  const csrf = inMemoryCsrfToken || getCookie('admin_csrf_token');
  return csrf ? { 'X-CSRF-Token': csrf } : {};
}

/** Раньше access JWT держали в памяти; теперь только httpOnly cookie — оставлено для совместимости импортов. */
export function setAdminAccessToken(_token: string | null) {
  void _token;
}

export function setAdminCsrfToken(token: string | null) {
  inMemoryCsrfToken = token;
}

export function clearAdminSession() {
  inMemoryCsrfToken = null;
  localStorage.removeItem('admin_user_id');
  localStorage.removeItem('admin_type');
}

async function refreshAdminAccessToken(): Promise<RefreshResult> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = axios
    .post(`${API_BASE_URL}/users/admin/refresh`, new URLSearchParams(), {
      withCredentials: true,
      headers: {
        ...csrfHeaders(),
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    .then((res) => {
      if (res.status === 200 && res.data?.user_id != null) {
        const csrf = getCookie('admin_csrf_token');
        if (csrf) inMemoryCsrfToken = String(csrf);
        if (res.data?.user_id != null) localStorage.setItem('admin_user_id', String(res.data.user_id));
        if (res.data?.admin_type) localStorage.setItem('admin_type', String(res.data.admin_type));
        return { renewed: true, definitiveFailure: false };
      }
      return { renewed: false, definitiveFailure: true };
    })
    .catch((err) => {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        if (status === 401 || status === 403) {
          return { renewed: false, definitiveFailure: true };
        }
      }
      return { renewed: false, definitiveFailure: false };
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

function shouldTryRefresh(error: any): boolean {
  const url: string = String(error?.config?.url || '');
  if (url.includes('/users/admin/refresh')) return false;
  return error?.response?.status === 401;
}

apiClient.interceptors.request.use(
  (config) => {
    const method = String(config.method || 'get').toLowerCase();
    if (method !== 'get' && method !== 'head' && method !== 'options') {
      const csrf = inMemoryCsrfToken || getCookie('admin_csrf_token');
      if (csrf) {
        config.headers['X-CSRF-Token'] = csrf;
      }
    }
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }
    if (config.data instanceof URLSearchParams) {
      config.headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config || {};
    if (shouldTryRefresh(error) && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshResult = await refreshAdminAccessToken();
      if (refreshResult.renewed) {
        originalRequest.headers = originalRequest.headers || {};
        const csrf = inMemoryCsrfToken || getCookie('admin_csrf_token');
        if (csrf) {
          originalRequest.headers['X-CSRF-Token'] = csrf;
        }
        delete originalRequest.headers.Authorization;
        return apiClient(originalRequest);
      }
      if (!refreshResult.definitiveFailure) {
        return Promise.reject(error);
      }
      clearAdminSession();
    }

    return Promise.reject(error);
  }
);

export default apiClient;
