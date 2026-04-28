import { TelegramBrowserLoginPanel } from './TelegramBrowserLoginPanel';

/**
 * Реестр способов входа в браузерной версии. Добавляйте сюда новые { id, Component }.
 * Порядок в массиве = порядок блоков на странице.
 */
export const browserLoginMethods = [{ id: 'telegram', Component: TelegramBrowserLoginPanel }];
