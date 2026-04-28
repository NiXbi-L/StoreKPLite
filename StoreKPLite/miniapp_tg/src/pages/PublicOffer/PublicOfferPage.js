import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { isTelegramWebAppEnvironment } from '../../utils/telegramEnvironment';
import '../Policy/PolicyPage.css';

export default function PublicOfferPage() {
  const navigate = useNavigate();
  const { setTabBarVisible } = useTabBarVisibility();
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const backButton =
    typeof window !== 'undefined' && isTelegramWebAppEnvironment() ? window.Telegram?.WebApp?.BackButton : null;
  const isTelegram = Boolean(backButton);

  useEffect(() => {
    setTabBarVisible(false);
    return () => setTabBarVisible(true);
  }, [setTabBarVisible]);

  useEffect(() => {
    if (backButton) {
      backButton.show();
      backButton.onClick(() => navigate(-1));
      return () => backButton.hide();
    }
  }, [backButton, navigate]);

  useEffect(() => {
    const url = (process.env.PUBLIC_URL || '') + '/public-offer.md';
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error('Не удалось загрузить документ');
        return res.text();
      })
      .then((text) => {
        setContent(text);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Ошибка загрузки');
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="policy-page">
      <header className="policy-page__header">
        {!isTelegram && (
          <button
            type="button"
            className="policy-page__back"
            onClick={() => navigate(-1)}
            aria-label="Назад"
          >
            ← Назад
          </button>
        )}
        <h1 className="policy-page__title">Договор публичной оферты</h1>
      </header>
      <div className="policy-page__body">
        {loading && <p className="policy-page__loading">Загрузка…</p>}
        {error && <p className="policy-page__error">{error}</p>}
        {!loading && !error && content && (
          <div className="policy-page__content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
