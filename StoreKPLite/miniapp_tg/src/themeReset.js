/**
 * Сброс инлайн-стилей темы Telegram / старой тёмной темы.
 * Палитра только из index.css (:root).
 */
const INLINE_THEME_VAR_KEYS = [
  '--bg-primary',
  '--bg-secondary',
  '--bg-tertiary',
  '--text-primary',
  '--text-secondary',
  '--text-tertiary',
  '--text-disabled',
  '--input-label',
  '--border-light',
  '--border-medium',
  '--border-heavy',
  '--border-focus',
  '--border-error',
  '--card-bg',
  '--card-border',
  '--card-shadow',
  '--accent',
  '--accent-hover',
  '--accent-muted',
  '--button-primary-bg',
  '--button-primary-hover',
  '--button-primary-pressed',
  '--button-primary-text',
  '--button-secondary-bg',
  '--button-secondary-border',
  '--button-secondary-hover',
  '--button-secondary-text',
  '--button-ghost-hover',
  '--input-bg',
  '--input-bg-disabled',
  '--input-border',
  '--input-border-hover',
  '--input-border-focus',
  '--input-border-error',
  '--input-placeholder',
  '--input-text',
  '--text-dark-primary',
  '--text-dark-secondary',
  '--text-dark-tertiary',
  '--button-spinner-ring',
  '--button-spinner-top',
];

export function resetDocumentThemeOverrides() {
  const root = document.documentElement;
  root.classList.remove('theme-tg', 'theme-dark');
  root.style.colorScheme = 'light';
  INLINE_THEME_VAR_KEYS.forEach((k) => root.style.removeProperty(k));
  document.body.style.removeProperty('background-color');
  document.body.style.removeProperty('color');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', '#ffffff');
}
