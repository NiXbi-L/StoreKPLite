import React from 'react';
import { useNavigate } from 'react-router-dom';
import './WebGuestAuthPlaceholder.css';

export default function WebGuestAuthPlaceholder({
  title = 'Вход в аккаунт',
  message = 'Этот раздел доступен после авторизации. Каталог и карточки товаров можно смотреть без входа.',
}) {
  const navigate = useNavigate();

  return (
    <div className="web-guest-auth-placeholder">
      <div className="web-guest-auth-placeholder__card">
        <h1 className="web-guest-auth-placeholder__title">{title}</h1>
        <p className="web-guest-auth-placeholder__text">{message}</p>
        <button
          type="button"
          className="web-guest-auth-placeholder__btn"
          onClick={() => navigate('/browser-login')}
        >
          Войти
        </button>
        <button
          type="button"
          className="web-guest-auth-placeholder__link"
          onClick={() => navigate('/main/catalog')}
        >
          Перейти в каталог
        </button>
      </div>
    </div>
  );
}
