import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductCard from '../../components/ProductCard';
import { fetchLikedPage, fetchItemTypes, removeItemAction } from '../../api/products';
import { useAuth } from '../../contexts/AuthContext';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { formatRublesPlain } from '../../utils/formatRubles';
import { clearStartappItemRoot } from '../../utils/startappItemEntry';
import '../Catalog/CatalogPage.css';
import './LikedPage.css';

const PAGE_SIZE = 20;

/** Нормализует элемент с API (FeedItemResponse) под формат ProductCard */
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
    liked: true,
    item_type: apiItem.item_type ?? '',
    item_type_id: apiItem.item_type_id ?? null,
    description: apiItem.description ?? '',
  };
}

/** Разворачивает ответ лайков: группы в отдельные товары, одиночные — как есть */
function flattenLikedResponse(list) {
  const out = [];
  for (const row of list || []) {
    if (row.group_items && row.group_items.length > 0) {
      row.group_items.forEach((it) => out.push(it));
    } else {
      out.push(row);
    }
  }
  return out;
}

export default function LikedPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const { setTabBarVisible } = useTabBarVisibility();
  const bodyScrollRef = useRef(null);
  const sentinelRef = useRef(null);
  const [items, setItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchValue, setSearchValue] = useState('');
  const searchQueryRef = useRef('');
  const [itemTypes, setItemTypes] = useState([]);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const filterPanelRef = useRef(null);
  const [appliedItemTypeIds, setAppliedItemTypeIds] = useState([]);
  const [appliedPriceMin, setAppliedPriceMin] = useState(null);
  const [appliedPriceMax, setAppliedPriceMax] = useState(null);
  const [appliedIsLegit, setAppliedIsLegit] = useState(null);
  const [draftItemTypeIds, setDraftItemTypeIds] = useState([]);
  const [draftPriceMin, setDraftPriceMin] = useState('');
  const [draftPriceMax, setDraftPriceMax] = useState('');
  const [draftIsLegit, setDraftIsLegit] = useState(null);
  const draftFiltersRef = useRef({ itemTypeIds: [], priceMin: '', priceMax: '', isLegit: null });

  const buildFilters = useCallback(() => {
    const itemTypeIds = appliedItemTypeIds.length ? appliedItemTypeIds : undefined;
    return {
      q: searchQueryRef.current.trim() || undefined,
      itemTypeIds,
      priceMin: appliedPriceMin != null ? appliedPriceMin : undefined,
      priceMax: appliedPriceMax != null ? appliedPriceMax : undefined,
      isLegit:
        appliedIsLegit !== null && appliedIsLegit !== undefined ? appliedIsLegit : undefined,
    };
  }, [appliedItemTypeIds, appliedPriceMin, appliedPriceMax, appliedIsLegit]);

  const loadLiked = useCallback(async (offset, append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const filters = buildFilters();
      const data = await fetchLikedPage(offset, PAGE_SIZE, filters);
      const flat = flattenLikedResponse(data.items || []);
      const normalized = flat.map(normalizeItem).filter(Boolean);
      setItems((prev) => (append ? [...prev, ...normalized] : normalized));
      setTotalCount(typeof data.total === 'number' ? data.total : 0);
      setHasMore(!!data.has_more);
      setNextOffset(data.next_offset != null ? data.next_offset : offset + normalized.length);
    } catch (e) {
      if (!append) {
        setError(e.message || 'Ошибка загрузки');
        setItems([]);
        setTotalCount(0);
        setHasMore(false);
        setNextOffset(0);
      }
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [buildFilters]);

  useEffect(() => {
    let cancelled = false;
    fetchItemTypes()
      .then((list) => { if (!cancelled) setItemTypes(list || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    loadLiked(0, false);
  }, [loadLiked]);

  useEffect(() => {
    if (!hasMore || loadingMore || loading) return;
    const el = sentinelRef.current;
    const root = bodyScrollRef.current;
    if (!el || !root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore && !loading) {
          loadLiked(nextOffset, true);
        }
      },
      { root, rootMargin: '200px', threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, nextOffset, loadLiked]);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) {
      return () => {
        setTabBarVisible(true);
      };
    }
    const handleBack = () => {
      navigate(-1);
    };
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
      setTabBarVisible(true);
    };
  }, [navigate, setTabBarVisible]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    e.currentTarget?.querySelector?.('input')?.blur();
    searchQueryRef.current = searchValue.trim();
    loadLiked(0, false);
  };

  const handleSearchFocus = () => setTabBarVisible(false);
  const handleSearchBlur = () => setTabBarVisible(true);

  const openFilterPanel = () => {
    setDraftItemTypeIds([...appliedItemTypeIds]);
    setDraftPriceMin(appliedPriceMin != null ? String(appliedPriceMin) : '');
    setDraftPriceMax(appliedPriceMax != null ? String(appliedPriceMax) : '');
    setDraftIsLegit(appliedIsLegit);
    setFilterPanelOpen(true);
  };

  const applyFilters = () => {
    setAppliedItemTypeIds(Array.isArray(draftItemTypeIds) ? draftItemTypeIds : []);
    setAppliedPriceMin(draftPriceMin.trim() ? Number(draftPriceMin) : null);
    setAppliedPriceMax(draftPriceMax.trim() ? Number(draftPriceMax) : null);
    setAppliedIsLegit(draftIsLegit);
    setFilterPanelOpen(false);
  };

  useEffect(() => {
    if (!filterPanelOpen) return;
    const onOutside = (e) => {
      if (filterPanelRef.current && !filterPanelRef.current.contains(e.target)) {
        const d = draftFiltersRef.current;
        setAppliedItemTypeIds(Array.isArray(d.itemTypeIds) ? d.itemTypeIds : []);
        setAppliedPriceMin(d.priceMin.trim() ? Number(d.priceMin) : null);
        setAppliedPriceMax(d.priceMax.trim() ? Number(d.priceMax) : null);
        setAppliedIsLegit(d.isLegit);
        setFilterPanelOpen(false);
      }
    };
    document.addEventListener('click', onOutside, true);
    return () => document.removeEventListener('click', onOutside, true);
  }, [filterPanelOpen]);

  draftFiltersRef.current = { itemTypeIds: draftItemTypeIds, priceMin: draftPriceMin, priceMax: draftPriceMax, isLegit: draftIsLegit };

  const handleLikeClick = async (e, itemId) => {
    e.stopPropagation();
    setItems((prev) => prev.filter((it) => it.id !== itemId));
    setTotalCount((n) => Math.max(0, n - 1));
    try {
      await removeItemAction(itemId);
      if (user?.id) {
        try {
          sessionStorage.removeItem(`likesSummaryV1:like:${user.id}`);
        } catch {
          /* ignore */
        }
      }
    } catch {
      loadLiked(0, false);
    }
  };

  const handleCardClick = (item) => {
    if (!item) return;
    clearStartappItemRoot();
    navigate(`/main/catalog/${item.id}`, { state: { item } });
  };

  const activeFilterChips = [];
  if (appliedItemTypeIds && appliedItemTypeIds.length > 0) {
    const selectedTypes = itemTypes.filter((t) => appliedItemTypeIds.includes(t.id));
    selectedTypes.forEach((t) => {
      activeFilterChips.push({
        key: `type-${t.id}`,
        label: t.name,
        clear: () => setAppliedItemTypeIds((prev) => prev.filter((id) => id !== t.id)),
      });
    });
  }
  if (appliedPriceMin != null || appliedPriceMax != null) {
    const chipRub = (v) => (v != null ? formatRublesPlain(v) : '');
    const label = appliedPriceMin != null && appliedPriceMax != null
      ? `${chipRub(appliedPriceMin)}₽ - ${chipRub(appliedPriceMax)}₽`
      : appliedPriceMin != null ? `от ${chipRub(appliedPriceMin)}₽` : `до ${chipRub(appliedPriceMax)}₽`;
    activeFilterChips.push({
      key: 'price',
      label,
      clear: () => { setAppliedPriceMin(null); setAppliedPriceMax(null); },
    });
  }
  if (appliedIsLegit !== null) {
    activeFilterChips.push({
      key: 'legit',
      label: appliedIsLegit ? 'Оригинал' : 'Реплика',
      clear: () => setAppliedIsLegit(null),
    });
  }

  const bannerText =
    loading && items.length === 0 ? 'Понравившиеся …' : `Понравившиеся — ${totalCount}`;

  if (error && items.length === 0) {
    return (
      <div className="liked-page">
        <div className="liked-page__header">
          <div className="liked-page__banner">
            <span className="liked-page__banner-text">{bannerText}</span>
          </div>
          <div className="catalog-page__controls">
            <form className="catalog-page__search" onSubmit={handleSearchSubmit}>
              <input
                className="catalog-page__search-input"
                type="search"
                value={searchValue}
                onChange={(e) => { setSearchValue(e.target.value); searchQueryRef.current = e.target.value; }}
                onFocus={handleSearchFocus}
                onBlur={handleSearchBlur}
                placeholder="Поиск"
                enterKeyHint="search"
              />
            </form>
            <button type="button" className="catalog-page__filter-btn" aria-label="Фильтры" onClick={openFilterPanel} />
          </div>
        </div>
        <div className="liked-page__error">{error}</div>
      </div>
    );
  }

  return (
    <div className="liked-page">
      <div className="liked-page__header">
        <div className="liked-page__banner">
          <span className="liked-page__banner-text">{bannerText}</span>
        </div>
        <div className="catalog-page__controls">
          <form className="catalog-page__search" onSubmit={handleSearchSubmit}>
            <input
              className="catalog-page__search-input"
              type="search"
              value={searchValue}
              onChange={(e) => { setSearchValue(e.target.value); searchQueryRef.current = e.target.value; }}
              onFocus={handleSearchFocus}
              onBlur={handleSearchBlur}
              placeholder="Поиск"
              enterKeyHint="search"
            />
          </form>
          <button type="button" className="catalog-page__filter-btn" aria-label="Фильтры" onClick={openFilterPanel}>
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
                            if (e.target.checked) set.add(t.id);
                            else set.delete(t.id);
                            return Array.from(set);
                          });
                        }}
                      />
                      <span className="catalog-page__filter-type-label">{t.name}</span>
                    </label>
                  );
                })}
                <button type="button" className="catalog-page__filter-types-reset" onClick={() => setDraftItemTypeIds([])}>Все типы</button>
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
                <button type="button" className={`catalog-page__filter-legit-btn ${draftIsLegit === null ? 'catalog-page__filter-legit-btn--active' : ''}`} onClick={() => setDraftIsLegit(null)}>Все</button>
                <button type="button" className={`catalog-page__filter-legit-btn ${draftIsLegit === true ? 'catalog-page__filter-legit-btn--active' : ''}`} onClick={() => setDraftIsLegit(true)}>Оригинал</button>
                <button type="button" className={`catalog-page__filter-legit-btn ${draftIsLegit === false ? 'catalog-page__filter-legit-btn--active' : ''}`} onClick={() => setDraftIsLegit(false)}>Реплика</button>
              </div>
            </div>
            <button type="button" className="catalog-page__filter-apply" onClick={applyFilters}>Применить</button>
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
      <div className="liked-page__body" ref={bodyScrollRef}>
        {loading && items.length === 0 ? (
          <div className="liked-page__loading">Загрузка…</div>
        ) : items.length === 0 ? (
          <div className="liked-page__empty">
            Пока ничего нет. Добавляйте товары в избранное в каталоге.
          </div>
        ) : (
          <>
            <div className="liked-page__grid">
              {items.map((item) => (
                <div key={item.id} className="liked-page__card">
                  <ProductCard item={item} liked onLikeClick={handleLikeClick} onClick={() => handleCardClick(item)} />
                </div>
              ))}
            </div>
            {loadingMore ? <div className="liked-page__loading liked-page__loading--more">Ещё…</div> : null}
            <div ref={sentinelRef} className="liked-page__sentinel" aria-hidden="true" />
          </>
        )}
      </div>
    </div>
  );
}
