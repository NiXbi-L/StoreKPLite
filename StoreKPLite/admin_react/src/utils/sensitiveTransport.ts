/**
 * Транспорт чувствительных данных: не отправлять пароль открытой строкой в JSON/форме.
 * (В DevTools значение всё равно декодируется — это снижение «читаемости с первого взгляда», не криптозащита.)
 */

/** UTF-8 строка → стандартный Base64 (как в Python base64.b64decode). */
export function encodeUtf8Base64(plain: string): string {
  const bytes = new TextEncoder().encode(plain);
  let binary = '';
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary);
}

/** Тело входа админки: один параметр `credentials` = base64(JSON.stringify({ login, password })). */
export function encodeAdminLoginCredentials(login: string, password: string): string {
  return encodeUtf8Base64(JSON.stringify({ login, password }));
}
