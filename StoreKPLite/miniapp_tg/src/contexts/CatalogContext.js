import React, { createContext, useContext, useState, useCallback } from 'react';

const CatalogContext = createContext(null);

const defaultAppliedFilters = { itemTypeIds: [], priceMin: null, priceMax: null, isLegit: null };

/** Скролл каталога: внутри .catalog-page__body и/или у родителя .main-page__content (как на карточке товара). */
const defaultCatalogScroll = { body: 0, main: 0 };

export function CatalogProvider({ children }) {
  const [items, setItems] = useState([]);
  const [likedIds, setLikedIds] = useState(new Set());
  const [nextOffset, setNextOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [appliedFilters, setAppliedFiltersState] = useState(defaultAppliedFilters);
  const [catalogScroll, setCatalogScrollState] = useState(defaultCatalogScroll);

  const setLikedIdsFromCatalog = useCallback((updater) => {
    setLikedIds((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      return next instanceof Set ? next : new Set(next);
    });
  }, []);

  const setAppliedFilters = useCallback((valueOrUpdater) => {
    setAppliedFiltersState((prev) => {
      const next = typeof valueOrUpdater === 'function' ? valueOrUpdater(prev) : valueOrUpdater;
      return next ? { ...defaultAppliedFilters, ...next } : defaultAppliedFilters;
    });
  }, []);

  const setCatalogScroll = useCallback((valueOrUpdater) => {
    setCatalogScrollState((prev) => {
      const next = typeof valueOrUpdater === 'function' ? valueOrUpdater(prev) : valueOrUpdater;
      if (!next || typeof next !== 'object') return prev;
      return { ...prev, ...next };
    });
  }, []);

  const value = {
    items,
    setItems,
    likedIds,
    setLikedIds: setLikedIdsFromCatalog,
    nextOffset,
    setNextOffset,
    hasMore,
    setHasMore,
    loading,
    setLoading,
    loadingMore,
    setLoadingMore,
    error,
    setError,
    appliedFilters,
    setAppliedFilters,
    catalogScroll,
    setCatalogScroll,
  };

  return (
    <CatalogContext.Provider value={value}>
      {children}
    </CatalogContext.Provider>
  );
}

export function useCatalog() {
  const ctx = useContext(CatalogContext);
  if (!ctx) {
    throw new Error('useCatalog must be used within CatalogProvider');
  }
  return ctx;
}
