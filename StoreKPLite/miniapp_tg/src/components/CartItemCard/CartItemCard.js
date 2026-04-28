import React, { useState } from 'react';
import {
  setCartQuantityByItem,
  deleteCartItem,
} from '../../api/products';
import { formatRublesForUser } from '../../utils/formatRubles';
import './CartItemCard.css';

const SVG_WALLET = (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M10.5 2.25H1.5C1.30109 2.25 1.11032 2.32902 0.96967 2.46967C0.829018 2.61032 0.75 2.80109 0.75 3V9C0.75 9.19891 0.829018 9.38968 0.96967 9.53033C1.11032 9.67098 1.30109 9.75 1.5 9.75H10.5C10.6989 9.75 10.8897 9.67098 11.0303 9.53033C11.171 9.38968 11.25 9.19891 11.25 9V3C11.25 2.80109 11.171 2.61032 11.0303 2.46967C10.8897 2.32902 10.6989 2.25 10.5 2.25ZM10.5 3V4.125H1.5V3H10.5ZM10.5 9H1.5V4.875H10.5V9ZM9.75 7.875C9.75 7.97446 9.71049 8.06984 9.64017 8.14017C9.56984 8.21049 9.47446 8.25 9.375 8.25H7.875C7.77554 8.25 7.68016 8.21049 7.60983 8.14017C7.53951 8.06984 7.5 7.97446 7.5 7.875C7.5 7.77554 7.53951 7.68016 7.60983 7.60983C7.68016 7.53951 7.77554 7.5 7.875 7.5H9.375C9.47446 7.5 9.56984 7.53951 9.64017 7.60983C9.71049 7.68016 9.75 7.77554 9.75 7.875ZM6.75 7.875C6.75 7.97446 6.71049 8.06984 6.64017 8.14017C6.56984 8.21049 6.47446 8.25 6.375 8.25H5.625C5.52554 8.25 5.43016 8.21049 5.35984 8.14017C5.28951 8.06984 5.25 7.97446 5.25 7.875C5.25 7.77554 5.28951 7.68016 5.35984 7.60983C5.43016 7.53951 5.52554 7.5 5.625 7.5H6.375C6.47446 7.5 6.56984 7.53951 6.64017 7.60983C6.71049 7.68016 6.75 7.77554 6.75 7.875Z" fill="white" />
  </svg>
);

const SVG_ARROW = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M3 5L7 9L11 5" stroke="#525252" />
  </svg>
);

const SVG_MINUS = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M14 8C14 8.13261 13.9473 8.25979 13.8536 8.35355C13.7598 8.44732 13.6326 8.5 13.5 8.5H2.5C2.36739 8.5 2.24021 8.44732 2.14645 8.35355C2.05268 8.25979 2 8.13261 2 8C2 7.86739 2.05268 7.74021 2.14645 7.64645C2.24021 7.55268 2.36739 7.5 2.5 7.5H13.5C13.6326 7.5 13.7598 7.55268 13.8536 7.64645C13.9473 7.74021 14 7.86739 14 8Z" fill="#737373" />
  </svg>
);

const SVG_PLUS = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M14 8C14 8.13261 13.9473 8.25979 13.8536 8.35355C13.7598 8.44732 13.6326 8.5 13.5 8.5H8.5V13.5C8.5 13.6326 8.44732 13.7598 8.35355 13.8536C8.25979 13.9473 8.13261 14 8 14C7.86739 14 7.74021 13.9473 7.64645 13.8536C7.55268 13.7598 7.5 13.6326 7.5 13.5V8.5H2.5C2.36739 8.5 2.24021 8.44732 2.14645 8.35355C2.05268 8.25979 2 8.13261 2 8C2 7.86739 2.05268 7.74021 2.14645 7.64645C2.24021 7.55268 2.36739 7.5 2.5 7.5H7.5V2.5C7.5 2.36739 7.55268 2.24021 7.64645 2.14645C7.74021 2.05268 7.86739 2 8 2C8.13261 2 8.25979 2.05268 8.35355 2.14645C8.44732 2.24021 8.5 2.36739 8.5 2.5V7.5H13.5C13.6326 7.5 13.7598 7.55268 13.8536 7.64645C13.9473 7.74021 14 7.86739 14 8Z" fill="#525252" />
  </svg>
);

const SVG_TRASH = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor" />
  </svg>
);

function SVGRadioSelected({ id }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g clipPath={`url(#clip_sel_${id})`}>
        <circle cx="7" cy="7" r="4.5" stroke="#171717" strokeWidth="5" />
      </g>
      <defs>
        <clipPath id={`clip_sel_${id}`}>
          <rect width="14" height="14" fill="white" />
        </clipPath>
      </defs>
    </svg>
  );
}

function SVGRadioUnselected({ id }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g clipPath={`url(#clip_un_${id})`}>
        <circle cx="7" cy="7" r="6.5" stroke="#171717" />
      </g>
      <defs>
        <clipPath id={`clip_un_${id}`}>
          <rect width="14" height="14" fill="white" />
        </clipPath>
      </defs>
    </svg>
  );
}

function toNumber(value) {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/\s/g, '').replace(',', '.'));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export default function CartItemCard({
  cartItem,
  selected,
  onSelect,
  onQuantityChange,
  onDeleted,
  onSizeChange,
}) {
  const { id: cartItemId, item, size, quantity, price_rub } = cartItem;
  const [qtyUpdating, setQtyUpdating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [sizeOpen, setSizeOpen] = useState(false);
  const [sizeDirection, setSizeDirection] = useState('down');

  const imageSrc = item?.photo ? `/${item.photo}` : null;
  const name = item?.name || 'Товар';
  const sizes = Array.isArray(item?.size)
    ? item.size.map((s) => String(s).trim()).filter(Boolean)
    : typeof item?.size === 'string'
      ? item.size.split(',').map((s) => s.trim()).filter(Boolean)
      : [];
  const displaySize = size != null && size !== '' ? size : (sizes[0] || '—');
  const unitPrice = toNumber(price_rub ?? item?.fixed_price_rub ?? item?.price_rub ?? 0);
  const hasFixedPrice = toNumber(item?.fixed_price_rub) != null;

  const handleQty = async (delta) => {
    if (delta > 0 && quantity >= 50) {
      onQuantityChange?.(cartItem, quantity, 'limit');
      return;
    }
    const newQty = Math.max(0, (quantity || 0) + delta);
    if (newQty === 0) {
      try {
        setDeleting(true);
        await deleteCartItem(cartItemId);
        onDeleted?.(cartItemId);
      } finally {
        setDeleting(false);
      }
      return;
    }
    try {
      setQtyUpdating(true);
      await setCartQuantityByItem(item.id, size || null, newQty);
      onQuantityChange?.(cartItem, newQty);
    } finally {
      setQtyUpdating(false);
    }
  };

  const stop = (e) => e.stopPropagation();
  const decideDirection = (buttonRect) => {
    if (typeof window === 'undefined') return 'down';
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const spaceBelow = viewportHeight - buttonRect.bottom;
    return spaceBelow < 360 ? 'up' : 'down';
  };

  return (
    <article
      className="cart-card"
      onClick={() => onSelect?.(cartItemId)}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(cartItemId); } }}
    >
      <button
        type="button"
        className="cart-card__delete"
        onClick={(e) => {
          stop(e);
          deleteCartItem(cartItemId).then(() => onDeleted?.(cartItemId));
        }}
        disabled={deleting}
        aria-label="Удалить из корзины"
      >
        {SVG_TRASH}
      </button>
      <div className="cart-card__photo">
        {imageSrc ? <img src={imageSrc} alt="" className="cart-card__photo-img" /> : null}
        <div className="cart-card__photo-cut" />
        <button
          type="button"
          className="cart-card__radio"
          onClick={(e) => { stop(e); onSelect?.(cartItemId); }}
          aria-checked={selected}
          aria-label={selected ? 'Снять выбор' : 'Выбрать'}
        >
          {selected ? <SVGRadioSelected id={cartItemId} /> : <SVGRadioUnselected id={cartItemId} />}
        </button>
      </div>
      <div className="cart-card__info">
        <div className="cart-card__price-badge">
          <span className="cart-card__price-icon">{SVG_WALLET}</span>
          <span className="cart-card__price-text">
            {hasFixedPrice ? '' : '~'}{unitPrice != null ? formatRublesForUser(unitPrice) : '—'}
          </span>
        </div>
        <h3 className="cart-card__name">{name}</h3>

        <div className="cart-card__controls" onClick={stop}>
          <div className="cart-card__controls-selects">
            {sizes.length > 0 ? (
              <div className="cart-card__select-wrap">
                <button
                  type="button"
                  className="cart-card__select cart-card__select--size"
                  onClick={(e) => {
                    stop(e);
                    const rect = e.currentTarget.getBoundingClientRect();
                    setSizeDirection(decideDirection(rect));
                    setSizeOpen((prev) => !prev);
                  }}
                  aria-expanded={sizeOpen}
                >
                  <span className="cart-card__select-text">{displaySize}</span>
                  <span className="cart-card__select-icon">{SVG_ARROW}</span>
                </button>
                {sizeOpen ? (
                  <ul className={`cart-card__dropdown cart-card__dropdown--${sizeDirection}`}>
                    {sizes.map((s) => (
                      <li key={s}>
                        <button
                          type="button"
                          className="cart-card__dropdown-item"
                          onClick={(e) => {
                            stop(e);
                            setSizeOpen(false);
                            onSizeChange?.(cartItem, s);
                          }}
                        >
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="cart-card__qty">
            <button type="button" className="cart-card__qty-btn" onClick={(e) => { stop(e); handleQty(-1); }} disabled={qtyUpdating}>{SVG_MINUS}</button>
            <div className="cart-card__qty-input">
              <span className="cart-card__qty-text">{quantity}</span>
            </div>
            <button type="button" className="cart-card__qty-btn" onClick={(e) => { stop(e); handleQty(1); }} disabled={qtyUpdating}>{SVG_PLUS}</button>
          </div>
        </div>
      </div>
    </article>
  );
}
