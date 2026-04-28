import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { hasTelegramWebAppInitData } from '../../utils/telegramEnvironment';
import WebGuestAuthPlaceholder from '../WebGuestAuthPlaceholder/WebGuestAuthPlaceholder';

/**
 * В WebView Telegram — дети без проверки (авторизация по initData).
 * В браузере без пользователя — заглушка с кнопкой входа.
 */
export default function RequireWebUser({ children }) {
  const { user, loading } = useAuth();

  if (hasTelegramWebAppInitData()) {
    return children;
  }

  if (loading) {
    return (
      <div className="app app--loading">
        <p>Загрузка…</p>
      </div>
    );
  }

  if (!user) {
    return <WebGuestAuthPlaceholder />;
  }

  return children;
}
