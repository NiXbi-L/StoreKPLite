import React, { useEffect, useCallback, useRef, useState, useLayoutEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductCard from '../../components/ProductCard';
import { fetchCatalogPage, fetchItemTypes, performItemAction, removeItemAction } from '../../api/products';
import { useCatalog } from '../../contexts/CatalogContext';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { formatRublesPlain } from '../../utils/formatRubles';
import { clearStartappItemRoot } from '../../utils/startappItemEntry';
import { useRequireWebLogin } from '../../hooks/useRequireWebLogin';
import { track } from '../../utils/productAnalytics';
import './CatalogPage.css';

const PAGE_SIZE = 20;

/** Нормализует товар с API под формат ProductCard: size — массив, photos — массив с file_path */
function normalizeItem(apiItem) {
  if (!apiItem) return null;
  const size = apiItem.size != null
    ? (Array.isArray(apiItem.size) ? apiItem.size : String(apiItem.size).split(',').map((s) => s.trim()).filter(Boolean))
    : [];
  return {
    id: apiItem.id,
    name: apiItem.name ?? '',
    price_rub: apiItem.price_rub != null ? Number(apiItem.price_rub) : null,
    size,
    photos: Array.isArray(apiItem.photos) ? apiItem.photos : [],
    liked: typeof apiItem.liked === 'boolean' ? apiItem.liked : undefined,
  };
}

export default function CatalogPage() {
  const requireWebLogin = useRequireWebLogin();
  const {
    items,
    setItems,
    likedIds,
    setLikedIds,
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
    appliedFilters: savedFilters,
    setAppliedFilters,
    catalogScroll: savedCatalogScroll,
    setCatalogScroll,
  } = useCatalog();

  const sentinelRef = useRef(null);
  /** Внутренний скролл сетки; наружный — .main-page__content (как на карточке товара). */
  const bodyScrollRef = useRef(null);
  const initialFetchDone = useRef(false);
  const filterPanelRef = useRef(null);
  const draftFiltersRef = useRef({ itemTypeIds: [], priceMin: '', priceMax: '' });
  const { setTabBarVisible } = useTabBarVisibility();
  const [searchValue, setSearchValue] = useState('');
  const searchQueryRef = useRef('');
  const [itemTypes, setItemTypes] = useState([]);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [appliedItemTypeIds, setAppliedItemTypeIds] = useState(() => (Array.isArray(savedFilters?.itemTypeIds) ? savedFilters.itemTypeIds : []));
  const [appliedPriceMin, setAppliedPriceMin] = useState(() => (savedFilters?.priceMin != null ? savedFilters.priceMin : null));
  const [appliedPriceMax, setAppliedPriceMax] = useState(() => (savedFilters?.priceMax != null ? savedFilters.priceMax : null));
  const [appliedIsLegit, setAppliedIsLegit] = useState(() => (savedFilters?.isLegit !== undefined ? savedFilters.isLegit : null)); // null - все, true - оригинал, false - реплика
  const [draftItemTypeIds, setDraftItemTypeIds] = useState([]);
  const [draftPriceMin, setDraftPriceMin] = useState('');
  const [draftPriceMax, setDraftPriceMax] = useState('');
  const [draftIsLegit, setDraftIsLegit] = useState(null);
  const restoredScrollRef = useRef(false);
  draftFiltersRef.current = { itemTypeIds: draftItemTypeIds, priceMin: draftPriceMin, priceMax: draftPriceMax, isLegit: draftIsLegit };

  // Синхронизация применённых фильтров в контекст, чтобы при перезаходе на каталог плашки восстанавливались
  useEffect(() => {
    setAppliedFilters({
      itemTypeIds: appliedItemTypeIds,
      priceMin: appliedPriceMin,
      priceMax: appliedPriceMax,
      isLegit: appliedIsLegit,
    });
  }, [appliedItemTypeIds, appliedPriceMin, appliedPriceMax, appliedIsLegit, setAppliedFilters]);
  const navigate = useNavigate();

  const getMainContentEl = () => document.querySelector('.main-page__content');

  const readScrollSnapshot = useCallback(() => {
    const mainEl = getMainContentEl();
    return {
      body: bodyScrollRef.current ? bodyScrollRef.current.scrollTop : 0,
      main: mainEl ? mainEl.scrollTop : 0,
    };
  }, []);

  const applyScrollSnapshot = useCallback((snap) => {
    const mainEl = getMainContentEl();
    const b = Math.max(0, Math.floor(Number(snap?.body) || 0));
    const m = Math.max(0, Math.floor(Number(snap?.main) || 0));
    if (bodyScrollRef.current) bodyScrollRef.current.scrollTop = b;
    if (mainEl) mainEl.scrollTop = m;
  }, []);

  const zeroCatalogScrollSurfaces = useCallback(() => {
    const mainEl = getMainContentEl();
    if (bodyScrollRef.current) bodyScrollRef.current.scrollTop = 0;
    if (mainEl) mainEl.scrollTop = 0;
    setCatalogScroll({ body: 0, main: 0 });
  }, [setCatalogScroll]);

  const loadPage = useCallback(async (offset, append = false, overrides = {}) => {
    const q = overrides.q !== undefined ? overrides.q : searchQueryRef.current;
    const itemTypeIds = overrides.itemTypeIds !== undefined ? overrides.itemTypeIds : appliedItemTypeIds;
    const priceMin = overrides.priceMin !== undefined ? overrides.priceMin : appliedPriceMin;
    const priceMax = overrides.priceMax !== undefined ? overrides.priceMax : appliedPriceMax;
    const isLegit = overrides.isLegit !== undefined ? overrides.isLegit : appliedIsLegit;
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const data = await fetchCatalogPage(offset, PAGE_SIZE, q, itemTypeIds, priceMin, priceMax, isLegit);
      const newItems = (data.items || []).map(normalizeItem).filter(Boolean);

      // Обновляем список товаров
      setItems((prev) => (append ? [...prev, ...newItems] : newItems));

      // Если бэкенд вернул liked, синхронизируем локальный список лайков
      const pageLikedIds = new Set(newItems.filter((it) => it.liked).map((it) => it.id));
      setLikedIds((prev) => {
        if (append) {
          const merged = new Set(prev);
          pageLikedIds.forEach((id) => merged.add(id));
          return merged;
        }
        return pageLikedIds;
      });
      setHasMore(!!data.has_more);
      setNextOffset(data.next_offset != null ? data.next_offset : offset + newItems.length);
      track('catalog_fetch', {
        offset,
        append,
        items_count: newItems.length,
        has_more: !!data.has_more,
        q: (q || '').slice(0, 120),
        item_type_ids_count: Array.isArray(itemTypeIds) ? itemTypeIds.length : 0,
        has_price: priceMin != null || priceMax != null,
        is_legit: isLegit,
      });
    } catch (e) {
      setError(e.message || 'Ошибка загрузки каталога');
      if (!append) setItems([]);
      track('catalog_fetch_error', {
        offset,
        append,
        message: String(e?.message || e || '').slice(0, 200),
      });
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [setItems, setHasMore, setNextOffset, setLoading, setLoadingMore, setError, appliedItemTypeIds, appliedPriceMin, appliedPriceMax, appliedIsLegit]);

  useEffect(() => {
    let cancelled = false;
    fetchItemTypes()
      .then((list) => { if (!cancelled) setItemTypes(list || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Первый запрос только если в кеше ещё нет товаров (пришли на вкладку впервые в этой сессии)
  useEffect(() => {
    if (items.length > 0) return; // уже есть данные из прошлого захода на вкладку
    if (initialFetchDone.current) return;
    initialFetchDone.current = true;
    loadPage(0, false);
  }, [items.length, loadPage]);

  useEffect(() => {
    const bodyEl = bodyScrollRef.current;
    const mainEl = getMainContentEl();
    if (!bodyEl && !mainEl) return undefined;
    let rafId = null;
    const saveScroll = () => {
      if (rafId != null) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        setCatalogScroll(readScrollSnapshot());
      });
    };
    if (bodyEl) bodyEl.addEventListener('scroll', saveScroll, { passive: true });
    if (mainEl) mainEl.addEventListener('scroll', saveScroll, { passive: true });
    return () => {
      if (bodyEl) bodyEl.removeEventListener('scroll', saveScroll);
      if (mainEl) mainEl.removeEventListener('scroll', saveScroll);
      if (rafId != null) {
        window.cancelAnimationFrame(rafId);
      }
      // Не вызываем setCatalogScroll здесь: к моменту cleanup уже может быть другая страница
      // в .main-page__content — перезапишем позицию каталога неверными 0.
    };
  }, [setCatalogScroll, readScrollSnapshot]);

  useLayoutEffect(() => {
    if (restoredScrollRef.current) return;
    if (loading) return;
    if (items.length === 0) return;
    if (!bodyScrollRef.current) return;
    restoredScrollRef.current = true;
    const snap = savedCatalogScroll || { body: 0, main: 0 };
    applyScrollSnapshot(snap);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        applyScrollSnapshot(snap);
      });
    });
  }, [items.length, loading, savedCatalogScroll, applyScrollSnapshot]);

  useEffect(() => {
    if (!hasMore || loadingMore || loading) return;
    const el = sentinelRef.current;
    if (!el) return;
    const bodyRoot = bodyScrollRef.current;
    const mainRoot = getMainContentEl();
    const root =
      bodyRoot && bodyRoot.scrollHeight > bodyRoot.clientHeight + 2 ? bodyRoot : mainRoot;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore && !loading) {
          loadPage(nextOffset, true);
        }
      },
      { root, rootMargin: '200px', threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, nextOffset, loadPage]);

  const handleLikeClick = async (e, itemId) => {
    e.stopPropagation();
    if (!requireWebLogin()) return;
    const currentlyLiked = likedIds.has(itemId);

    // Оптимистичное обновление UI
    setLikedIds((prev) => {
      const next = new Set(prev);
      if (currentlyLiked) next.delete(itemId);
      else next.add(itemId);
      return next;
    });

    try {
      if (currentlyLiked) {
        await removeItemAction(itemId);
      } else {
        await performItemAction(itemId, 'like');
      }
    } catch (err) {
      // В случае ошибки откатываем локальное состояние
      setLikedIds((prev) => {
        const next = new Set(prev);
        if (currentlyLiked) next.add(itemId);
        else next.delete(itemId);
        return next;
      });
    }
  };

  const handleCardClick = (item) => {
    if (!item) return;
    setCatalogScroll(readScrollSnapshot());
    clearStartappItemRoot();
    navigate(`/main/catalog/${item.id}`, { state: { item } });
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    e.currentTarget?.querySelector?.('input')?.blur();
    searchQueryRef.current = searchValue.trim();
    // При изменении поискового запроса начинаем с первой страницы
    initialFetchDone.current = false;
    restoredScrollRef.current = true;
    zeroCatalogScrollSurfaces();
    setItems([]);
    setHasMore(true);
    setNextOffset(0);
    loadPage(0, false);
  };

  const handleSearchFocus = () => {
    setTabBarVisible(false);
  };

  const handleSearchBlur = () => {
    setTabBarVisible(true);
  };

  const openFilterPanel = () => {
    setDraftItemTypeIds(appliedItemTypeIds || []);
    setDraftPriceMin(appliedPriceMin != null ? String(appliedPriceMin) : '');
    setDraftPriceMax(appliedPriceMax != null ? String(appliedPriceMax) : '');
    setDraftIsLegit(appliedIsLegit);
    setFilterPanelOpen(true);
  };

  const applyFilters = () => {
    const it = Array.isArray(draftItemTypeIds) ? draftItemTypeIds.map((id) => Number(id)) : [];
    const pMin = draftPriceMin.trim() ? Number(draftPriceMin) : null;
    const pMax = draftPriceMax.trim() ? Number(draftPriceMax) : null;
    const legit = draftIsLegit;
    setAppliedItemTypeIds(it);
    setAppliedPriceMin(pMin);
    setAppliedPriceMax(pMax);
    setAppliedIsLegit(legit);
    setFilterPanelOpen(false);
    initialFetchDone.current = false;
    restoredScrollRef.current = true;
    zeroCatalogScrollSurfaces();
    setItems([]);
    setHasMore(true);
    setNextOffset(0);
    loadPage(0, false, {
      q: searchQueryRef.current,
      itemTypeIds: it,
      priceMin: pMin,
      priceMax: pMax,
      isLegit: legit,
    });
  };

  useEffect(() => {
    if (!filterPanelOpen) return;
    const onOutside = (e) => {
      if (filterPanelRef.current && !filterPanelRef.current.contains(e.target)) {
        const d = draftFiltersRef.current;
        const it = Array.isArray(d.itemTypeIds) ? d.itemTypeIds.map((id) => Number(id)) : [];
        const pMin = d.priceMin.trim() ? Number(d.priceMin) : null;
        const pMax = d.priceMax.trim() ? Number(d.priceMax) : null;
        const legit = d.isLegit;
        setAppliedItemTypeIds(it);
        setAppliedPriceMin(pMin);
        setAppliedPriceMax(pMax);
        setAppliedIsLegit(legit);
        setFilterPanelOpen(false);
        initialFetchDone.current = false;
        restoredScrollRef.current = true;
        zeroCatalogScrollSurfaces();
        setItems([]);
        setHasMore(true);
        setNextOffset(0);
        loadPage(0, false, { q: searchQueryRef.current, itemTypeIds: it, priceMin: pMin, priceMax: pMax, isLegit: legit });
      }
    };
    document.addEventListener('click', onOutside, true);
    return () => document.removeEventListener('click', onOutside, true);
  }, [filterPanelOpen, loadPage, setItems, setHasMore, setNextOffset, zeroCatalogScrollSurfaces]);

  const activeFilterChips = [];
  if (appliedItemTypeIds && appliedItemTypeIds.length > 0) {
    const selectedTypes = itemTypes.filter((t) => appliedItemTypeIds.includes(t.id));
    selectedTypes.forEach((t) => {
      activeFilterChips.push({
        key: `type-${t.id}`,
        label: t.name,
        clear: () => {
          const nextIds = appliedItemTypeIds.filter((id) => id !== t.id);
          setAppliedItemTypeIds(nextIds);
          restoredScrollRef.current = true;
          zeroCatalogScrollSurfaces();
          setItems([]); setHasMore(true); setNextOffset(0); initialFetchDone.current = false;
          loadPage(0, false, {
            q: searchQueryRef.current,
            itemTypeIds: nextIds,
            priceMin: appliedPriceMin,
            priceMax: appliedPriceMax,
          });
        },
      });
    });
  }
  if (appliedPriceMin != null || appliedPriceMax != null) {
    const chipRub = (v) => (v != null ? formatRublesPlain(v) : '');
    const label = appliedPriceMin != null && appliedPriceMax != null
      ? `${chipRub(appliedPriceMin)}₽ - ${chipRub(appliedPriceMax)}₽`
      : appliedPriceMin != null ? `от ${chipRub(appliedPriceMin)}₽` : `до ${chipRub(appliedPriceMax)}₽`;
    activeFilterChips.push({ key: 'price', label, clear: () => {
      setAppliedPriceMin(null); setAppliedPriceMax(null);
      restoredScrollRef.current = true;
      zeroCatalogScrollSurfaces();
      setItems([]); setHasMore(true); setNextOffset(0); initialFetchDone.current = false;
      loadPage(0, false, { q: searchQueryRef.current, itemTypeIds: appliedItemTypeIds, priceMin: null, priceMax: null, isLegit: appliedIsLegit });
    } });
  }

  if (appliedIsLegit !== null) {
    const label = appliedIsLegit ? 'Оригинал' : 'Реплика';
    activeFilterChips.push({
      key: 'legit',
      label,
      clear: () => {
        setAppliedIsLegit(null);
        restoredScrollRef.current = true;
        zeroCatalogScrollSurfaces();
        setItems([]); setHasMore(true); setNextOffset(0); initialFetchDone.current = false;
        loadPage(0, false, { q: searchQueryRef.current, itemTypeIds: appliedItemTypeIds, priceMin: appliedPriceMin, priceMax: appliedPriceMax, isLegit: null });
      },
    });
  }

  if (error && items.length === 0) {
    return (
      <div className="catalog-page">
        <div className="catalog-page__header">
          <div className="catalog-page__controls">
            <form className="catalog-page__search" onSubmit={handleSearchSubmit}>
              <input
                className="catalog-page__search-input"
                type="search"
                value={searchValue}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchValue(value);
                  searchQueryRef.current = value;
                }}
                onFocus={handleSearchFocus}
                onBlur={handleSearchBlur}
                placeholder="Поиск"
                enterKeyHint="search"
              />
            </form>
            <button
              type="button"
              className="catalog-page__filter-btn"
              aria-label="Фильтры"
              onClick={(e) => { e.stopPropagation(); openFilterPanel(); }}
            >
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path d="M28.825 6.19128C28.6711 5.83567 28.416 5.53315 28.0915 5.32135C27.767 5.10955 27.3875 4.99781 27 5.00003H4.99997C4.61288 5.0008 4.23433 5.11387 3.91025 5.32554C3.58616 5.53721 3.33047 5.83838 3.17418 6.19251C3.01789 6.54664 2.96772 6.93852 3.02977 7.3206C3.09181 7.70268 3.2634 8.05855 3.52372 8.34503L3.53372 8.35628L12 17.3963V27C11.9999 27.362 12.098 27.7172 12.284 28.0278C12.4699 28.3384 12.7366 28.5927 13.0557 28.7636C13.3748 28.9345 13.7343 29.0155 14.0958 28.9982C14.4574 28.9808 14.8075 28.8657 15.1087 28.665L19.1087 25.9975C19.3829 25.8149 19.6078 25.5673 19.7632 25.2769C19.9187 24.9864 20 24.662 20 24.3325V17.3963L28.4675 8.35628L28.4775 8.34503C28.7405 8.05986 28.9138 7.70352 28.9756 7.32049C29.0374 6.93747 28.985 6.54472 28.825 6.19128ZM18.2725 16.3225C18.0995 16.5059 18.0021 16.7479 18 17V24.3325L14 27V17C14 16.7461 13.9035 16.5017 13.73 16.3163L4.99997 7.00003H27L18.2725 16.3225Z" fill="white" />
              </svg>
            </button>
          </div>
          {activeFilterChips.length > 0 && (
            <div className="catalog-page__filters">
              {activeFilterChips.map((chip) => (
                <div key={chip.key} className="catalog-page__filter-chip">
                  <span className="catalog-page__filter-chip-text">{chip.label}</span>
                  <button type="button" className="catalog-page__filter-chip-remove" onClick={chip.clear} aria-label="Сбросить" />
                </div>
              ))}
            </div>
          )}
        </div>
        <div ref={bodyScrollRef} className="catalog-page__body catalog-page__body--error">
          <div className="catalog-page__error">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="catalog-page">
      <div className="catalog-page__header">
        <div className="catalog-page__controls">
          <form className="catalog-page__search" onSubmit={handleSearchSubmit}>
            <input
                className="catalog-page__search-input"
                type="search"
                value={searchValue}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchValue(value);
                  searchQueryRef.current = value;
                }}
                onFocus={handleSearchFocus}
                onBlur={handleSearchBlur}
                placeholder="Поиск"
                enterKeyHint="search"
              />
          </form>
          <button
            type="button"
            className="catalog-page__filter-btn"
            aria-label="Фильтры"
            onClick={(e) => { e.stopPropagation(); openFilterPanel(); }}
          >
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M28.825 6.19128C28.6711 5.83567 28.416 5.53315 28.0915 5.32135C27.767 5.10955 27.3875 4.99781 27 5.00003H4.99997C4.61288 5.0008 4.23433 5.11387 3.91025 5.32554C3.58616 5.53721 3.33047 5.83838 3.17418 6.19251C3.01789 6.54664 2.96772 6.93852 3.02977 7.3206C3.09181 7.70268 3.2634 8.05855 3.52372 8.34503L3.53372 8.35628L12 17.3963V27C11.9999 27.362 12.098 27.7172 12.284 28.0278C12.4699 28.3384 12.7366 28.5927 13.0557 28.7636C13.3748 28.9345 13.7343 29.0155 14.0958 28.9982C14.4574 28.9808 14.8075 28.8657 15.1087 28.665L19.1087 25.9975C19.3829 25.8149 19.6078 25.5673 19.7632 25.2769C19.9187 24.9864 20 24.662 20 24.3325V17.3963L28.4675 8.35628L28.4775 8.34503C28.7405 8.05986 28.9138 7.70352 28.9756 7.32049C29.0374 6.93747 28.985 6.54472 28.825 6.19128ZM18.2725 16.3225C18.0995 16.5059 18.0021 16.7479 18 17V24.3325L14 27V17C14 16.7461 13.9035 16.5017 13.73 16.3163L4.99997 7.00003H27L18.2725 16.3225Z" fill="white" />
            </svg>
          </button>
        </div>
        {filterPanelOpen && (
          <div ref={filterPanelRef} className="catalog-page__filter-panel" onClick={(e) => e.stopPropagation()}>
            <div className="catalog-page__filter-panel-row">
              <label className="catalog-page__filter-label">Тип вещи</label>
              <div className="catalog-page__filter-types">
                {itemTypes.map((t) => {
                  const checked = draftItemTypeIds.includes(t.id);
                  return (
                    <label key={t.id} className="catalog-page__filter-type">
                      <input
                        type="checkbox"
                        className="catalog-page__filter-type-checkbox"
                        checked={checked}
                        onChange={(e) => {
                          setDraftItemTypeIds((prev) => {
                            const set = new Set(prev);
                            if (e.target.checked) {
                              set.add(t.id);
                            } else {
                              set.delete(t.id);
                            }
                            return Array.from(set);
                          });
                        }}
                      />
                      <span className="catalog-page__filter-type-label">{t.name}</span>
                    </label>
                  );
                })}
                <button
                  type="button"
                  className="catalog-page__filter-types-reset"
                  onClick={() => setDraftItemTypeIds([])}
                >
                  Все типы
                </button>
              </div>
            </div>
            <div className="catalog-page__filter-panel-row">
              <label className="catalog-page__filter-label">Цена (₽)</label>
              <div className="catalog-page__filter-price">
                <input
                  type="number"
                  className="catalog-page__filter-input"
                  placeholder="Мин"
                  min={0}
                  value={draftPriceMin}
                  onChange={(e) => setDraftPriceMin(e.target.value)}
                  onFocus={handleSearchFocus}
                  onBlur={handleSearchBlur}
                />
                <span className="catalog-page__filter-price-sep">–</span>
                <input
                  type="number"
                  className="catalog-page__filter-input"
                  placeholder="Макс"
                  min={0}
                  value={draftPriceMax}
                  onChange={(e) => setDraftPriceMax(e.target.value)}
                  onFocus={handleSearchFocus}
                  onBlur={handleSearchBlur}
                />
              </div>
            </div>
            <div className="catalog-page__filter-panel-row">
              <label className="catalog-page__filter-label">Тип товара</label>
              <div className="catalog-page__filter-legit">
                <button
                  type="button"
                  className={`catalog-page__filter-legit-btn ${draftIsLegit === null ? 'catalog-page__filter-legit-btn--active' : ''}`}
                  onClick={() => setDraftIsLegit(null)}
                >
                  Все
                </button>
                <button
                  type="button"
                  className={`catalog-page__filter-legit-btn ${draftIsLegit === true ? 'catalog-page__filter-legit-btn--active' : ''}`}
                  onClick={() => setDraftIsLegit(true)}
                >
                  Оригинал
                </button>
                <button
                  type="button"
                  className={`catalog-page__filter-legit-btn ${draftIsLegit === false ? 'catalog-page__filter-legit-btn--active' : ''}`}
                  onClick={() => setDraftIsLegit(false)}
                >
                  Реплика
                </button>
              </div>
            </div>
            <button type="button" className="catalog-page__filter-apply" onClick={applyFilters}>
              Применить
            </button>
          </div>
        )}
        {activeFilterChips.length > 0 && (
          <div className="catalog-page__filters">
            {activeFilterChips.map((chip) => (
              <div key={chip.key} className="catalog-page__filter-chip">
                <span className="catalog-page__filter-chip-text">{chip.label}</span>
                <button type="button" className="catalog-page__filter-chip-remove" onClick={chip.clear} aria-label="Сбросить" />
              </div>
            ))}
          </div>
        )}
      </div>
      <div ref={bodyScrollRef} className="catalog-page__body">
        {loading && items.length === 0 ? (
          <div className="catalog-page__loading">Загрузка каталога…</div>
        ) : (
          <>
            <div className="catalog-page__grid">
              {items.map((item) => (
                <div key={item.id} className="catalog-page__card">
                  <ProductCard
                    item={item}
                    liked={likedIds.has(item.id)}
                    onLikeClick={handleLikeClick}
                    onClick={() => handleCardClick(item)}
                  />
                </div>
              ))}
            </div>
            <div ref={sentinelRef} className="catalog-page__sentinel" aria-hidden="true" />
            {loadingMore && <div className="catalog-page__loading-more">Загрузка…</div>}
          </>
        )}
      </div>
    </div>
  );
}
