import React from 'react';
import './BrowserNavBackButton.css';

/**
 * Кнопка «назад» для браузерной версии: визуально близко к нативной BackButton в полноэкранном TG Mini App.
 */
export default function BrowserNavBackButton({ onClick, className = '', ...rest }) {
  return (
    <button
      type="button"
      className={`browser-nav-back${className ? ` ${className}` : ''}`}
      onClick={onClick}
      aria-label="Назад"
      {...rest}
    >
      <svg className="browser-nav-back__icon" viewBox="0 0 24 24" width="24" height="24" aria-hidden>
        <path
          fill="currentColor"
          d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"
        />
      </svg>
    </button>
  );
}
