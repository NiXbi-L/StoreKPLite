/**
 * Вычисляет длину caption как её считает Telegram после парсинга HTML.
 * В HTML режиме: <a href="url">text</a> — в лимит 1024 входит только видимый текст "text", не url и не теги.
 */
export function getTelegramCaptionLength(html: string): number {
  if (!html) return 0;
  // Заменяем <a href="...">текст</a> на текст (видимая часть ссылки)
  const withoutLinks = html.replace(/<a\s+href="[^"]*">([^<]*)<\/a>/gi, '$1');
  // Удаляем оставшиеся HTML-теги
  const plainText = withoutLinks.replace(/<[^>]+>/g, '');
  return plainText.length;
}

export const TELEGRAM_CAPTION_MAX_LENGTH = 1024;
