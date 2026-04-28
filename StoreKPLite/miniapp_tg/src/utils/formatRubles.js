/**
 * Целое число рублей для отображения (без суффикса «₽»), с округлением.
 */
export function formatRublesPlain(value) {
  if (value == null || value === '') return '';
  const n = Number(value);
  if (!Number.isFinite(n)) return '';
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(n));
}

/**
 * Сумма в рублях для отображения пользователю: без копеек (округление до целого).
 * Расчёты и API могут оставаться с копейками.
 */
export function formatRublesForUser(value) {
  const plain = formatRublesPlain(value);
  return plain === '' ? '' : `${plain} ₽`;
}
