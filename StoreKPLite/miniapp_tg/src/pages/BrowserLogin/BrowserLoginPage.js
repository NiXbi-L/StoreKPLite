import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { browserLoginMethods } from './browserLoginRegistry';
import './BrowserLoginPage.css';

export default function BrowserLoginPage() {
  const { guestHtml } = useAuth();

  if (guestHtml != null) {
    return (
      <div className="browser-login-page browser-login-page--restricted">
        <div className="browser-login-page__shell">
          <p className="browser-login-page__restricted-text">Сейчас доступ ограничен.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="browser-login-page">
      <div className="browser-login-page__shell">
        <header className="browser-login-page__hero">
          <p className="browser-login-page__brand">MatchWear</p>
          <h1 className="browser-login-page__title">Вход в аккаунт</h1>
          <p className="browser-login-page__subtitle">
            Выберите способ входа. Данные защищены так же, как в приложении Telegram.
          </p>
        </header>

        <section className="browser-login-page__methods" aria-label="Способы входа">
          {browserLoginMethods.map(({ id, Component }) => (
            <Component key={id} />
          ))}
        </section>

        <footer className="browser-login-page__footer">
          <p className="browser-login-page__footer-note">
            Продолжая, вы соглашаетесь с{' '}
            <Link to="/public-offer" className="browser-login-page__legal-link">
              условиями сервиса
            </Link>{' '}
            и{' '}
            <Link to="/policy" className="browser-login-page__legal-link">
              политикой конфиденциальности
            </Link>
            .
          </p>
        </footer>
      </div>
    </div>
  );
}
