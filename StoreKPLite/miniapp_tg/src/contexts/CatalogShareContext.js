import { createContext } from 'react';

/**
 * Состояние «поделиться» для карточки товара (браузер): MainPage рисует кнопку, CatalogItem задаёт payload.
 * @type {React.Context<React.Dispatch<React.SetStateAction<{ itemId: number, title: string } | null>> | null>}
 */
export const CatalogShareDispatchContext = createContext(null);
