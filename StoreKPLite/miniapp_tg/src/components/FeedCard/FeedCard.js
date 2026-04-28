import React from 'react';
import { formatRublesForUser } from '../../utils/formatRubles';
import './FeedCard.css';

/**
 * Карточка товара для ленты: большое фото, индикаторы фото, градиентный контент на всю площадь.
 * rotationClass: '' | 'like-active' | 'dislike-active' для поворота при удержании (лайк/дизлайк).
 * exitAnimation: '' | 'left' | 'right' — анимация улетания карточки.
 */
export default function FeedCard({ item, rotationClass = '', photoIndex = 0, exitAnimation = '' }) {
  if (!item) return null;

  const photos = Array.isArray(item.photos) ? item.photos : [];
  const photoList = photos.filter((p) => p && p.file_path);
  const currentPhoto = photoList[photoIndex] ?? photoList[0];
  const src = currentPhoto?.file_path ? `/${currentPhoto.file_path}` : null;

  const priceFormatted =
    item.price_rub != null ? formatRublesForUser(item.price_rub) : '';

  let mod = '';
  if (exitAnimation === 'right') mod = ' feed-card--exit-right';
  else if (exitAnimation === 'left') mod = ' feed-card--exit-left';
  else if (rotationClass === 'like-active') mod = ' feed-card--like-active';
  else if (rotationClass === 'dislike-active') mod = ' feed-card--dislike-active';

  return (
    <article
      className={`feed-card${mod}`.trim()}
      role="article"
      aria-label={item.name || 'Товар'}
    >
      <div
        className="feed-card__bg"
        style={src ? { backgroundImage: `url(${src})` } : undefined}
        aria-hidden="true"
      />
      {photoList.length > 1 && (
        <div className="feed-card__indicators" aria-hidden="true">
          {photoList.map((_, i) => (
            <span
              key={i}
              className={`feed-card__indicator ${i === photoIndex ? 'feed-card__indicator--active' : ''}`}
            />
          ))}
        </div>
      )}
      <div className="feed-card__content-wrap">
        <div className="feed-card__content">
          <h2 className="feed-card__title" title={item.name || ''}>
            {item.name || '—'}
          </h2>
          {priceFormatted && (
            <p className="feed-card__price">Цена: {priceFormatted}</p>
          )}
        </div>
      </div>
    </article>
  );
}
