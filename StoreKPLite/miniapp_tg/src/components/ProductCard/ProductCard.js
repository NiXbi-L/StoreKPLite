import React from 'react';
import { LikeButton } from '../Button';
import { formatRublesForUser } from '../../utils/formatRubles';
import './ProductCard.css';

/**
 * Форматирует массив размеров: если все числовые — выводит диапазон "37 - 45", иначе перечисление через запятую.
 * @param {string[]|null|undefined} size
 * @returns {string}
 */
function formatSizes(size) {
  if (!size || !Array.isArray(size) || size.length === 0) return '';
  const trimmed = size.map((s) => String(s).trim()).filter(Boolean);
  if (trimmed.length === 0) return '';
  const numeric = trimmed.map((s) => parseFloat(s)).filter((n) => !Number.isNaN(n));
  const allNumeric = numeric.length === trimmed.length;
  if (allNumeric && numeric.length > 0) {
    const min = Math.min(...numeric);
    const max = Math.max(...numeric);
    return min === max ? String(min) : `${min} - ${max}`;
  }
  return trimmed.join(', ');
}

/**
 * Карточка товара по макету: фон — первое фото, поверх градиент и контент (название, цена, размеры), кнопка лайка в углу.
 * Размер задаётся контейнером; пропорции сохраняются через aspect-ratio (180/239).
 *
 * @param {Object} item - Данные товара: { id, name, price_rub, size?, imageUrl?, photos? }
 * @param {boolean} [liked=false] - Лайкнут ли товар
 * @param {function} [onLikeClick] - Обработчик клика по кнопке лайка (event, itemId)
 * @param {function} [onClick] - Обработчик клика по карточке (itemId)
 * @param {string} [className] - Дополнительные CSS-классы
 */
export default function ProductCard({
  item,
  liked = false,
  onLikeClick,
  onClick,
  className = '',
  ...rest
}) {
  if (!item) return null;

  const { id, name, price_rub, size, imageUrl, photos } = item;
  const src = imageUrl || (photos && photos[0]?.file_path) ? `/${(photos && photos[0]?.file_path) || imageUrl}` : null;

  const priceFormatted = price_rub != null ? formatRublesForUser(price_rub) : '';
  const sizesStr = formatSizes(size);
  const sizesDisplay = sizesStr ? `Размеры: ${sizesStr}` : '';

  const handleCardClick = () => {
    if (onClick) onClick(id);
  };

  const handleKeyDown = (e) => {
    if (onClick && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onClick(id);
    }
  };

  const handleLikeClick = (e) => {
    e.stopPropagation();
    if (onLikeClick) onLikeClick(e, id);
  };

  return (
    <article
      className={`product-card ${className}`.trim()}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      {...rest}
    >
      <div
        className="product-card__bg"
        style={src ? { backgroundImage: `url(${src})` } : undefined}
        aria-hidden="true"
      />
      <div className="product-card__overlay">
        <div className="product-card__content">
          <h3 className="product-card__title" title={name || ''}>
            {name || '—'}
          </h3>
          {priceFormatted && (
            <p className="product-card__price">Цена: {priceFormatted}</p>
          )}
          {sizesDisplay && (
            <p className="product-card__sizes">{sizesDisplay}</p>
          )}
        </div>
      </div>
      <div className="product-card__like-wrap">
        <LikeButton liked={liked} onClick={handleLikeClick} />
      </div>
    </article>
  );
}
