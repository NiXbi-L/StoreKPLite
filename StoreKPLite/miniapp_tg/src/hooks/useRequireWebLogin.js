import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { hasTelegramWebAppInitData } from '../utils/telegramEnvironment';

/**
 * В Telegram миниаппе вход по initData; в обычном браузере без токена — редирект на /browser-login.
 * @returns {() => boolean} true если можно вызывать защищённые действия
 */
export function useRequireWebLogin() {
  const { user } = useAuth();
  const navigate = useNavigate();

  return useCallback(() => {
    if (hasTelegramWebAppInitData()) return true;
    if (user) return true;
    navigate('/browser-login');
    return false;
  }, [user, navigate]);
}
