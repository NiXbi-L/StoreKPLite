/**
 * Утилиты для авторизации (вход в админку).
 */

/**
 * Авторизация через API
 * @param loginValue - логин пользователя
 * @param password - пароль
 * @throws Error если авторизация не удалась
 */
export const login = async (loginValue: string, password: string): Promise<void> => {
  const formData = new FormData();
  formData.append('login', loginValue);
  formData.append('password', password);
  
  // Используем apiClient для единообразия (он использует относительный путь /api)
  // Но этот файл использует fetch напрямую, поэтому используем относительный путь
  const apiUrl = process.env.REACT_APP_ADMIN_API_URL || process.env.REACT_APP_API_URL || '/api';
  const response = await fetch(`${apiUrl}/users/admin/login`, {
    method: 'POST',
    body: formData,
    credentials: 'include', // Важно для работы с cookies (JWT токены)
  });
  
  if (!response.ok && response.status !== 302) {
    // Парсим HTML ответ для получения ошибки (если есть)
    const text = await response.text();
    throw new Error('Неверный логин или пароль');
  }
};
