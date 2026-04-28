import React from 'react';
import './Button.css';

/**
 * size: 'large' (50px) | 'small' (45px)
 * variant: 'primary' | 'secondary'
 * disabled: неактивный — opacity 80%
 * secondary всегда с opacity 80%
 */
export default function Button({
  children,
  size = 'large',
  variant = 'primary',
  disabled = false,
  loading = false,
  type = 'button',
  className = '',
  onClick,
  ...rest
}) {
  const classNames = [
    'btn',
    `btn--${size}`,
    `btn--${variant}`,
    disabled && 'btn--disabled',
    loading && 'btn--loading',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const isDisabled = disabled || loading;

  const handleClick = (event) => {
    if (isDisabled) return;
    if (onClick) onClick(event);
  };

  return (
    <button
      type={type}
      className={classNames}
      disabled={isDisabled}
      onClick={handleClick}
      {...rest}
    >
      {loading && <span className="btn__spinner" aria-hidden="true" />}
      <span className="btn__text">{children}</span>
    </button>
  );
}
