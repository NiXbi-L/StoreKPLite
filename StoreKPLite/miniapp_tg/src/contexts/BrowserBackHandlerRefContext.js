import React, { createContext, useContext, useRef } from 'react';

/**
 * Реф на обработчик «Назад» в браузере: дочерний экран (напр. карта ПВЗ) может подставить
 * свою логику вместо стандартного navigate(-1) в шапке MainPage.
 */
const BrowserBackHandlerRefContext = createContext(null);

export function BrowserBackHandlerRefProvider({ children }) {
  const ref = useRef(null);
  return <BrowserBackHandlerRefContext.Provider value={ref}>{children}</BrowserBackHandlerRefContext.Provider>;
}

export function useBrowserBackHandlerRef() {
  const ctx = useContext(BrowserBackHandlerRefContext);
  if (!ctx) {
    throw new Error('useBrowserBackHandlerRef must be used within BrowserBackHandlerRefProvider');
  }
  return ctx;
}
