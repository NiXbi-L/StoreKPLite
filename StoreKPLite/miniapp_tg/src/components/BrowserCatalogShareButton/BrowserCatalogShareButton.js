import React, { useCallback, useState } from 'react';
import { runCatalogShare, buildShareCatalogUrl } from '../../utils/catalogShare';
import './BrowserCatalogShareButton.css';

export default function BrowserCatalogShareButton({ itemId, title }) {
  const [hint, setHint] = useState(null);

  const onClick = useCallback(async () => {
    const id = Number(itemId);
    if (!Number.isFinite(id) || id <= 0) return;
    const shareUrl = buildShareCatalogUrl(id);
    try {
      const result = await runCatalogShare({ shareUrl, title });
      if (result === 'copied') {
        setHint('Скопировано');
        setTimeout(() => setHint(null), 2000);
      } else {
        setHint(null);
      }
    } catch {
      setHint('Ошибка');
      setTimeout(() => setHint(null), 2000);
    }
  }, [itemId, title]);

  return (
    <button
      type="button"
      className="browser-catalog-share"
      onClick={onClick}
      aria-label={hint === 'Скопировано' ? 'Ссылка скопирована' : 'Поделиться'}
    >
      <svg className="browser-catalog-share__icon" viewBox="0 0 24 24" width="24" height="24" aria-hidden>
        <path
          fill="currentColor"
          d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"
        />
      </svg>
      {hint ? <span className="browser-catalog-share__hint">{hint}</span> : null}
    </button>
  );
}
