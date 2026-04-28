import React, { useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import Button, { LikeButton } from '../../components/Button';
import {
  fetchItemById,
  performItemAction,
  removeItemAction,
  addToCart,
  setCartQuantityByItem,
  getItemReviewsSummary,
  fetchItemBuyoutQueue,
} from '../../api/products';
import PhotoGalleryModal from '../../components/PhotoGalleryModal';
import { formatRublesForUser } from '../../utils/formatRubles';
import {
  shouldShowStartappHomeForItem,
  clearStartappItemRoot,
  invalidateStartappItemRoot,
  syncStartappRootFromTelegramForItem,
} from '../../utils/startappItemEntry';
import { isTelegramWebAppEnvironment } from '../../utils/telegramEnvironment';
import { CatalogShareDispatchContext } from '../../contexts/CatalogShareContext';
import { useRequireWebLogin } from '../../hooks/useRequireWebLogin';
import { useMouseDragHorizontalScroll } from '../../hooks/useMouseDragHorizontalScroll';
import { track } from '../../utils/productAnalytics';
import './CatalogItemPage.css';

const STAR_FILL = '#171717';

function formatBuyoutDeadlineCountdown(remainingMs) {
  const ms = remainingMs;
  if (ms <= 0) return '00:00:00';
  const sec = Math.floor(ms / 1000);
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, '0');
  if (d > 0) return `${d}д ${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function productEntrySource(state) {
  if (!state || typeof state !== 'object') return 'direct';
  if (state.fromFeed) return 'feed';
  if (state.fromRelated) return 'related';
  if (state.fromOrders) return 'orders';
  if (state.fromStartappItem) return 'startapp';
  if (state.item) return 'catalog';
  return 'direct';
}

function StarIcon({ filled, white }) {
  const fill = white ? 'white' : STAR_FILL;
  if (filled) {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59188C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866Z" fill={fill} />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M14.9488 6.07866C14.8863 5.88649 14.7683 5.71712 14.6097 5.59189C14.4511 5.46665 14.259 5.39116 14.0575 5.37491L10.37 5.07741L8.94629 1.63429C8.8693 1.44667 8.73825 1.28619 8.56981 1.17325C8.40137 1.06031 8.20315 1 8.00035 1C7.79756 1 7.59934 1.06031 7.4309 1.17325C7.26246 1.28619 7.13141 1.44667 7.05442 1.63429L5.63192 5.07679L1.94254 5.37491C1.74078 5.39198 1.54854 5.4682 1.3899 5.59404C1.23127 5.71988 1.1133 5.88973 1.05077 6.08232C0.988239 6.27491 0.983936 6.48167 1.0384 6.67669C1.09286 6.87172 1.20366 7.04633 1.35692 7.17866L4.16942 9.60554L3.31254 13.2343C3.26462 13.4314 3.27635 13.6384 3.34625 13.8288C3.41615 14.0193 3.54107 14.1847 3.70514 14.304C3.86921 14.4234 4.06505 14.4913 4.26778 14.4991C4.47051 14.5069 4.671 14.4544 4.84379 14.348L8.00004 12.4055L11.1582 14.348C11.331 14.4531 11.5311 14.5047 11.7332 14.4962C11.9353 14.4878 12.1304 14.4198 12.2939 14.3007C12.4574 14.1816 12.5821 14.0168 12.6521 13.8271C12.7221 13.6373 12.7345 13.431 12.6875 13.2343L11.8275 9.60491L14.64 7.17804C14.7945 7.04593 14.9064 6.87094 14.9613 6.67522C15.0163 6.47951 15.0119 6.27189 14.9488 6.07866ZM13.99 6.42054L10.9463 9.04554C10.8769 9.10537 10.8252 9.18312 10.797 9.27031C10.7688 9.3575 10.7651 9.45076 10.7863 9.53991L11.7163 13.4649C11.7187 13.4703 11.7189 13.4765 11.717 13.482C11.715 13.4876 11.7109 13.4922 11.7057 13.4949C11.6944 13.5037 11.6913 13.5018 11.6819 13.4949L8.26192 11.3918C8.18315 11.3434 8.0925 11.3177 8.00004 11.3177C7.90758 11.3177 7.81693 11.3434 7.73817 11.3918L4.31817 13.4962C4.30879 13.5018 4.30629 13.5037 4.29442 13.4962C4.28914 13.4935 4.2851 13.4889 4.28312 13.4833C4.28115 13.4777 4.28139 13.4716 4.28379 13.4662L5.21379 9.54116C5.23499 9.45201 5.23127 9.35875 5.20306 9.27156C5.17484 9.18437 5.1232 9.10662 5.05379 9.04679L2.01004 6.42179C2.00254 6.41554 1.99567 6.40991 2.00192 6.39054C2.00817 6.37116 2.01317 6.37366 2.02254 6.37241L6.01754 6.04991C6.10917 6.04205 6.19686 6.00907 6.27096 5.9546C6.34506 5.90013 6.4027 5.82628 6.43754 5.74116L7.97629 2.01554C7.98129 2.00491 7.99817 1.99991 7.99817 1.99991C8.01317 1.99991 8.01504 2.00491 8.02004 2.01554L9.56254 5.74116C9.59771 5.82631 9.65572 5.90008 9.73016 5.95434C9.80461 6.00861 9.89259 6.04125 9.98442 6.04866L13.9794 6.37116C13.9888 6.37116 13.9944 6.37116 14 6.38929C14.0057 6.40741 14 6.41429 13.99 6.42054Z" fill={fill} />
    </svg>
  );
}

export default function CatalogItemPage() {
  const setCatalogSharePayload = useContext(CatalogShareDispatchContext);
  const requireWebLogin = useRequireWebLogin();
  const navigate = useNavigate();
  const { itemId } = useParams();
  const location = useLocation();
  const { setTabBarVisible } = useTabBarVisibility();
  const blockInAppNav = useMemo(
    () =>
      Boolean(
        location.state?.item ||
          location.state?.fromRelated ||
          location.state?.fromOrders
      ),
    [location.state]
  );
  const entrySource = useMemo(() => productEntrySource(location.state), [location.state]);
  const [showStartappHome, setShowStartappHome] = useState(() =>
    itemId ? shouldShowStartappHomeForItem(itemId) : false
  );

  useEffect(() => {
    if (!itemId) {
      setShowStartappHome(false);
      return;
    }
    const sync = () => {
      syncStartappRootFromTelegramForItem(itemId, blockInAppNav);
      setShowStartappHome(shouldShowStartappHomeForItem(itemId));
    };
    sync();
    const t1 = setTimeout(sync, 0);
    const t2 = setTimeout(sync, 100);
    const t3 = setTimeout(sync, 350);
    const t4 = setTimeout(sync, 900);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
    };
  }, [itemId, blockInAppNav]);

  const trackRef = useRef(null);
  const lastProductViewIdRef = useRef(null);
  const [item, setItem] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(true);
  const [detailsError, setDetailsError] = useState(null);
  const [photosReady, setPhotosReady] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sizeChartOpen, setSizeChartOpen] = useState(false);
  const [liked, setLiked] = useState(false);
  const [addToCartLoading, setAddToCartLoading] = useState(false);
  const [addToCartError, setAddToCartError] = useState(null);
  const [quantityUpdating, setQuantityUpdating] = useState(false);
  const [cartInputQty, setCartInputQty] = useState(0);
  const [selectedSize, setSelectedSize] = useState(null);
  const [reviewsSummary, setReviewsSummary] = useState({ average_rating: 0, total_count: 0 });
  const [photoGallery, setPhotoGallery] = useState(null);
  const [buyoutQueue, setBuyoutQueue] = useState(null);
  const [buyoutTimerTick, setBuyoutTimerTick] = useState(0);

  const inCart = Array.isArray(item?.in_cart) ? item.in_cart : [];
  const getCartQuantityForSize = (size) => {
    const key = size == null || size === '' ? null : String(size).trim();
    return inCart.reduce((sum, e) => {
      const eSize = e.size == null || e.size === '' ? null : String(e.size).trim();
      return eSize === key ? sum + (e.quantity || 0) : sum;
    }, 0);
  };
  const cartQtyForSelected = selectedSize != null && selectedSize !== '' ? getCartQuantityForSize(selectedSize) : getCartQuantityForSize(null);
  const showQuantityControls = selectedSize !== undefined && cartQtyForSelected > 0;

  useEffect(() => {
    setCartInputQty(cartQtyForSelected);
  }, [cartQtyForSelected]);

  const refreshItem = useCallback(async () => {
    if (!itemId) return;
    try {
      const data = await fetchItemById(itemId);
      setItem(data);
    } catch {
      // keep current item
    }
  }, [itemId]);

  useEffect(() => {
    if (!itemId) return;
    let cancelled = false;
    getItemReviewsSummary(itemId).then((data) => {
      if (!cancelled) setReviewsSummary(data || { average_rating: 0, total_count: 0 });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [itemId]);

  useEffect(() => {
    if (isTelegramWebAppEnvironment() || !setCatalogSharePayload) {
      return undefined;
    }
    const idNum = Number(itemId);
    if (!Number.isFinite(idNum) || idNum <= 0) {
      setCatalogSharePayload(null);
      return undefined;
    }
    setCatalogSharePayload({
      itemId: idNum,
      title: item?.name ? String(item.name).trim() : '',
    });
    return () => setCatalogSharePayload(null);
  }, [itemId, item?.name, setCatalogSharePayload]);

  useEffect(() => {
    setTabBarVisible(false);

    if (!isTelegramWebAppEnvironment()) {
      return () => {
        setTabBarVisible(true);
      };
    }

    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) {
      return () => {
        setTabBarVisible(true);
      };
    }

    if (showStartappHome) {
      backButton.hide();
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
  }, [navigate, setTabBarVisible, showStartappHome]);

  const title = (item && item.name) || (itemId ? `Товар ${itemId}` : '');
  const photos = Array.isArray(item?.photos) ? item.photos : [];
  const hasPhotos = photos.length > 0;
  const heroDragScroll = useMouseDragHorizontalScroll({
    disabled: !photosReady || photos.length <= 1,
  });

  // Размеры приходят как строка "37, 38, 39" или массив строк
  const rawSize = item && item.size;
  const sizes = Array.isArray(rawSize)
    ? rawSize.map((s) => String(s).trim()).filter(Boolean)
    : typeof rawSize === 'string'
      ? rawSize
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      : [];

  const toNumber = (value) => {
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
      const normalized = value.replace(/\s/g, '').replace(',', '.');
      const parsed = Number(normalized);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };

  const approxPrice = item ? toNumber(item.price_rub) : null;
  const fixedPrice = item ? toNumber(item.fixed_price_rub) : null;

  useEffect(() => {
    /* Очередь «Выкуп» нужна и для «Под заказ» (fixedPrice), и для «только ~цена» без наличия */
    if (!itemId || approxPrice == null) {
      setBuyoutQueue(null);
      return undefined;
    }
    const ac = new AbortController();
    (async () => {
      try {
        let revision;
        const snap = await fetchItemBuyoutQueue(itemId, { signal: ac.signal });
        if (ac.signal.aborted) return;
        setBuyoutQueue(snap);
        revision = snap.revision;
        while (!ac.signal.aborted) {
          const next = await fetchItemBuyoutQueue(itemId, {
            wait: true,
            revision,
            signal: ac.signal,
          });
          if (ac.signal.aborted) break;
          setBuyoutQueue(next);
          revision = next.revision;
        }
      } catch {
        if (!ac.signal.aborted) setBuyoutQueue(null);
      }
    })();
    return () => ac.abort();
  }, [itemId, approxPrice]);

  useEffect(() => {
    const g = buyoutQueue?.global_buyout_count;
    if (!buyoutQueue?.application_deadline_at || typeof g !== 'number' || g < 1) {
      return undefined;
    }
    const t = setInterval(() => setBuyoutTimerTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [buyoutQueue?.application_deadline_at, buyoutQueue?.global_buyout_count]);

  const buyoutGlobalCount =
    buyoutQueue != null && typeof buyoutQueue.global_buyout_count === 'number'
      ? buyoutQueue.global_buyout_count
      : 0;
  const buyoutItemCount =
    buyoutQueue != null && typeof buyoutQueue.count === 'number' ? buyoutQueue.count : 0;
  const buyoutShowTimer =
    buyoutQueue != null &&
    buyoutGlobalCount >= 1 &&
    Boolean(buyoutQueue.application_deadline_at);
  void buyoutTimerTick;
  const buyoutTimerLabel =
    buyoutShowTimer && buyoutQueue.application_deadline_at
      ? formatBuyoutDeadlineCountdown(
          Date.parse(buyoutQueue.application_deadline_at) - Date.now()
        )
      : '';
  const buyoutQueueHintText =
    buyoutItemCount >= 1 && fixedPrice != null
      ? ` · Уже ${buyoutItemCount} в очереди`
      : buyoutItemCount >= 1
        ? ` · Уже ${buyoutItemCount} заказали`
        : buyoutGlobalCount >= 1
          ? ' · Идёт набор общей партии'
          : null;

  const priceHistory = Array.isArray(item?.price_history) ? item.price_history : [];
  const groupItems = Array.isArray(item?.group_items) ? item.group_items : [];
  const currentItemId = item ? Number(item.id) : null;

  // При смене товара сбрасываем выбранный размер и состояние модалки
  useEffect(() => {
    setSelectedSize(null);
    setHistoryOpen(false);
  }, [itemId]);

  // При первом появлении размеров автоматически выбираем первый
  useEffect(() => {
    if (sizes.length > 0 && !selectedSize) {
      setSelectedSize(sizes[0]);
    }
  }, [sizes, selectedSize]);

  // Синхронизируем локальный like с данными бэкенда (если есть)
  useEffect(() => {
    if (item && typeof item.liked === 'boolean') {
      setLiked(item.liked);
    }
  }, [item]);

  // При переходе на новый товар через роутер (из каталога / рекомендаций)
  // используем данные из location.state как быстрый прелоад и включаем загрузку деталей
  useEffect(() => {
    const fromState = (location.state && location.state.item) || null;
    if (fromState) {
      setItem(fromState);
      setDetailsLoading(true);
    }
  }, [location.state]);

  useEffect(() => {
    lastProductViewIdRef.current = null;
  }, [itemId]);

  useEffect(() => {
    if (detailsLoading || !item?.id) return;
    const id = Number(item.id);
    if (!Number.isFinite(id)) return;
    if (lastProductViewIdRef.current === id) return;
    lastProductViewIdRef.current = id;
    track('product_view', {
      item_id: id,
      source: entrySource,
      group_id: item?.group_id ?? null,
    });
  }, [detailsLoading, item?.id, entrySource, item?.group_id]);

  // При переходе на товар «из рекомендаций» скроллим контент наверх
  useEffect(() => {
    if (location.state && location.state.fromRelated) {
      const contentEl = document.querySelector('.main-page__content');
      if (contentEl) {
        contentEl.scrollTop = 0;
      }
    }
  }, [location.state]);

  // Всегда обновляем данные товара по ID при заходе на страницу
  useEffect(() => {
    if (!itemId) return;

    let cancelled = false;
    setDetailsLoading(true);
    setDetailsError(null);

    fetchItemById(itemId)
      .then((data) => {
        if (cancelled) return;
        setItem(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setDetailsError(e.message || 'Ошибка загрузки товара');
      })
      .finally(() => {
        if (cancelled) return;
        setDetailsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [itemId]);

  // Ждём, пока все фото загрузятся, прежде чем монтировать карусель
  useEffect(() => {
    let cancelled = false;
    if (!item || !hasPhotos) {
      setPhotosReady(Boolean(item) && !hasPhotos);
      return () => {
        cancelled = true;
      };
    }

    setPhotosReady(false);
    const loaders = photos
      .filter((p) => p && p.file_path)
      .map((p) => new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve();
        img.onerror = () => resolve();
        img.src = `/${p.file_path}`;
      }));

    Promise.all(loaders).then(() => {
      if (!cancelled) {
        setPhotosReady(true);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [hasPhotos, photos]);

  // Всегда держим карусель в начале при заходе на экран / смене набора фото
  useEffect(() => {
    if (photosReady && trackRef.current) {
      trackRef.current.scrollLeft = 0;
    }
  }, [photosReady, photos.length]);

  return (
    <div className="item-page">
      <div className="item-page__hero">
        {showStartappHome && (
          <div className="item-page__hero-home">
            <button
              type="button"
              className="like-btn"
              aria-label="В каталог"
              onClick={() => {
                clearStartappItemRoot();
                navigate('/main/catalog');
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path
                  d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8h5z"
                  fill="white"
                />
              </svg>
            </button>
          </div>
        )}
        <div className="item-page__hero-like">
          <LikeButton
            liked={liked}
            onClick={async () => {
              if (!requireWebLogin()) return;
              const currentlyLiked = liked;
              setLiked(!currentlyLiked);
              if (!item) return;
              try {
                if (currentlyLiked) {
                  await removeItemAction(item.id);
                } else {
                  await performItemAction(item.id, 'like');
                }
              } catch (err) {
                // Откат при ошибке
                setLiked(currentlyLiked);
              }
            }}
          />
        </div>
        <div className="item-page__hero-overlay">
          <div className="item-page__hero-content">
            <div className="item-page__hero-bottom">
              <h1 className="item-page__hero-title" title={title}>
                {title}
              </h1>
            </div>
            {!photosReady && (
              <div className="item-page__hero-loading">
                <div className="item-page__hero-spinner" aria-hidden="true" />
              </div>
            )}
          </div>
        </div>
        {photosReady && (
          <div
            className={`item-page__hero-track ${photos.length === 1 ? 'item-page__hero-track--single' : ''}`.trim()}
            ref={trackRef}
            role="button"
            tabIndex={0}
            {...heroDragScroll.dragScrollProps}
            onClick={() => {
              if (heroDragScroll.consumeSuppressedClick()) return;
              if (!hasPhotos) return;
              let idx = 0;
              if (trackRef.current && photos.length > 1) {
                const w = trackRef.current.clientWidth;
                if (w > 0) idx = Math.round(trackRef.current.scrollLeft / w);
                idx = Math.max(0, Math.min(idx, photos.length - 1));
              }
              setPhotoGallery({
                photos: photos.map((p) => p.file_path),
                currentIndex: idx,
              });
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (hasPhotos) {
                  setPhotoGallery({
                    photos: photos.map((p) => p.file_path),
                    currentIndex: 0,
                  });
                }
              }
            }}
            aria-label={hasPhotos ? 'Открыть фото товара' : undefined}
          >
            {hasPhotos
              ? photos.map((photo, idx) => (
                  <div
                    key={photo.id || idx}
                    className={`item-page__hero-slide ${photos.length === 1 ? 'item-page__hero-slide--single' : ''}`.trim()}
                  >
                    {photo.file_path && (
                      <img
                        className="item-page__hero-img"
                        src={`/${photo.file_path}`}
                        alt={title || 'Фото товара'}
                      />
                    )}
                  </div>
                ))
              : (
                <div className="item-page__hero-slide item-page__hero-slide--single" />
              )}
          </div>
        )}
      </div>
      {approxPrice != null && (
        <div className="item-page__price">
          {fixedPrice != null ? (
            <>
              <div className="item-page__price-fixed">
                <span className="item-page__price-fixed-icon" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M14 3H2C1.73478 3 1.48043 3.10536 1.29289 3.29289C1.10536 3.48043 1 3.73478 1 4V12C1 12.2652 1.10536 12.5196 1.29289 12.7071C1.48043 12.8946 1.73478 13 2 13H14C14.2652 13 14.5196 12.8946 14.7071 12.7071C14.8946 12.5196 15 12.2652 15 12V4C15 3.73478 14.8946 3.48043 14.7071 3.29289C14.5196 3.10536 14.2652 3 14 3ZM14 4V5.5H2V4H14ZM14 12H2V6.5H14V12ZM13 10.5C13 10.6326 12.9473 10.7598 12.8536 10.8536C12.7598 10.9473 12.6326 11 12.5 11H10.5C10.3674 11 10.2402 10.9473 10.1464 10.8536C10.0527 10.7598 10 10.6326 10 10.5C10 10.3674 10.0527 10.2402 10.1464 10.1464C10.2402 10.0527 10.3674 10 10.5 10H12.5C12.6326 10 12.7598 10.0527 12.8536 10.1464C12.9473 10.2402 13 10.3674 13 10.5ZM9 10.5C9 10.6326 8.94732 10.7598 8.85355 10.8536C8.75979 10.9473 8.63261 11 8.5 11H7.5C7.36739 11 7.24021 10.9473 7.14645 10.8536C7.05268 10.7598 7 10.6326 7 10.5C7 10.3674 7.05268 10.2402 7.14645 10.1464C7.24021 10.0527 7.36739 10 7.5 10H8.5C8.63261 10 8.75979 10.0527 8.85355 10.1464C8.94732 10.2402 9 10.3674 9 10.5Z" fill="white" />
                  </svg>
                </span>
                <span className="item-page__price-fixed-text">
                  {formatRublesForUser(fixedPrice)}
                </span>
              </div>
              <div className="item-page__price-order-row">
                <div className="item-page__price-order-badge">
                  <span className="item-page__price-order-badge-text">Под заказ</span>
                </div>
                <div className="item-page__price-order-value-wrap">
                  <span className="item-page__price-order-value">
                    ~{formatRublesForUser(approxPrice)}
                  </span>
                  {buyoutQueueHintText != null && (
                    <span className="item-page__buyout-queue-hint">{buyoutQueueHintText}</span>
                  )}
                </div>
              </div>
              {buyoutShowTimer && (
                <div className="item-page__buyout-delivery-row" aria-live="polite">
                  <span className="item-page__buyout-delivery-badge">До поставки</span>
                  <span className="item-page__buyout-timer">{buyoutTimerLabel}</span>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="item-page__price-order-row item-page__price-order-row--single-price">
                <div className="item-page__price-fixed item-page__price-fixed--single">
                  <span className="item-page__price-fixed-icon" aria-hidden="true">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M14 3H2C1.73478 3 1.48043 3.10536 1.29289 3.29289C1.10536 3.48043 1 3.73478 1 4V12C1 12.2652 1.10536 12.5196 1.29289 12.7071C1.48043 12.8946 1.73478 13 2 13H14C14.2652 13 14.5196 12.8946 14.7071 12.7071C14.8946 12.5196 15 12.2652 15 12V4C15 3.73478 14.8946 3.48043 14.7071 3.29289C14.5196 3.10536 14.2652 3 14 3ZM14 4V5.5H2V4H14ZM14 12H2V6.5H14V12ZM13 10.5C13 10.6326 12.9473 10.7598 12.8536 10.8536C12.7598 10.9473 12.6326 11 12.5 11H10.5C10.3674 11 10.2402 10.9473 10.1464 10.8536C10.0527 10.7598 10 10.6326 10 10.5C10 10.3674 10.0527 10.2402 10.1464 10.1464C10.2402 10.0527 10.3674 10 10.5 10H12.5C12.6326 10 12.7598 10.0527 12.8536 10.1464C12.9473 10.2402 13 10.3674 13 10.5ZM9 10.5C9 10.6326 8.94732 10.7598 8.85355 10.8536C8.75979 10.9473 8.63261 11 8.5 11H7.5C7.36739 11 7.24021 10.9473 7.14645 10.8536C7.05268 10.7598 7 10.6326 7 10.5C7 10.3674 7.05268 10.2402 7.14645 10.1464C7.24021 10.0527 7.36739 10 7.5 10H8.5C8.63261 10 8.75979 10.0527 8.85355 10.1464C8.94732 10.2402 9 10.3674 9 10.5Z" fill="white" />
                    </svg>
                  </span>
                  <span className="item-page__price-fixed-text">
                    ~{formatRublesForUser(approxPrice)}
                  </span>
                </div>
                {buyoutQueueHintText != null && (
                  <span className="item-page__buyout-queue-hint">{buyoutQueueHintText}</span>
                )}
              </div>
              {buyoutShowTimer && (
                <div className="item-page__buyout-delivery-row" aria-live="polite">
                  <span className="item-page__buyout-delivery-badge">До поставки</span>
                  <span className="item-page__buyout-timer">{buyoutTimerLabel}</span>
                </div>
              )}
            </>
          )}
          {((typeof item?.is_legit === 'boolean' && !item.is_legit) ||
            (item?.photo_promo_badge && String(item.photo_promo_badge).trim())) && (
            <div className="item-page__price-badges">
              {typeof item?.is_legit === 'boolean' && !item.is_legit && (
                <div className="item-page__price-replica">
                  <span className="item-page__price-replica-text">Реплика</span>
                </div>
              )}
              {item?.photo_promo_badge && String(item.photo_promo_badge).trim() && (
                <div className="item-page__price-photo-promo">
                  <span className="item-page__price-photo-promo-text" title={String(item.photo_promo_badge).trim()}>
                    {String(item.photo_promo_badge).trim()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      <div className="item-page__meta">
        <button
          type="button"
          className="item-page__reviews-button"
          onClick={() => navigate(`/main/catalog/${itemId}/reviews`)}
        >
          <span className="item-page__reviews-main">
            <span className="item-page__reviews-star" aria-hidden="true">
              <StarIcon filled white />
            </span>
            <span className="item-page__reviews-rating">
              {reviewsSummary.total_count > 0 ? Number(reviewsSummary.average_rating).toFixed(2) : '—'}
            </span>
          </span>
          <span className="item-page__reviews-count">
            {reviewsSummary.total_count === 0 ? 'Нет отзывов' : `${reviewsSummary.total_count} ${reviewsSummary.total_count === 1 ? 'отзыв' : reviewsSummary.total_count < 5 ? 'отзыва' : 'отзывов'}`}
          </span>
        </button>
        <div className="item-page__meta-buttons">
          <Button
            size="small"
            variant="secondary"
            className="item-page__meta-btn"
            onClick={() => setHistoryOpen(true)}
          >
            История цен
          </Button>
          {item?.size_chart && (
            <Button
              size="small"
              variant="secondary"
              className="item-page__meta-btn"
              onClick={() => setSizeChartOpen(true)}
            >
              Размерная сетка
            </Button>
          )}
        </div>
      </div>
      {sizes.length > 0 && (
        <div className="item-page__sizes">
          {sizes.map((size) => (
            <button
              key={size}
              type="button"
              className={`item-page__size ${selectedSize === size ? 'item-page__size--active' : ''}`.trim()}
              onClick={() => setSelectedSize(size)}
            >
              <span className="item-page__size-text">{size}</span>
            </button>
          ))}
        </div>
      )}
      {groupItems.length > 0 && (
        <div className="item-page__group">
          <div className="item-page__group-scroll">
            {groupItems.map((groupItem) => {
              const firstPhoto = Array.isArray(groupItem.photos) && groupItem.photos.length > 0 ? groupItem.photos[0] : null;
              const isCurrent = currentItemId != null && Number(groupItem.id) === currentItemId;
              return (
                <button
                  key={groupItem.id}
                  type="button"
                  className={`item-page__group-card ${isCurrent ? 'item-page__group-card--current' : ''}`.trim()}
                  onClick={() => {
                    invalidateStartappItemRoot();
                    navigate(`/main/catalog/${groupItem.id}`, { state: { item: groupItem } });
                  }}
                >
                  {firstPhoto?.file_path ? (
                    <img
                      className="item-page__group-card-img"
                      src={`/${firstPhoto.file_path}`}
                      alt={groupItem.name || ''}
                    />
                  ) : (
                    <span className="item-page__group-card-placeholder" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {historyOpen && (
        <PriceHistoryModal
          onClose={() => setHistoryOpen(false)}
          history={priceHistory}
        />
      )}
      {sizeChartOpen && item?.size_chart && (
        <SizeChartModal
          onClose={() => setSizeChartOpen(false)}
          sizeChart={item.size_chart}
        />
      )}
      {photoGallery && (
        <PhotoGalleryModal
          photos={photoGallery.photos}
          currentIndex={photoGallery.currentIndex}
          onClose={() => setPhotoGallery(null)}
        />
      )}
      <div className="item-page__add-to-cart">
        {addToCartError && (
          <p className="item-page__add-to-cart-error" role="alert">
            {addToCartError}
          </p>
        )}
        {showQuantityControls ? (
          <div className="item-page__cart-quantity">
            <button
              type="button"
              className="item-page__cart-qty-btn"
              aria-label="Уменьшить количество"
              disabled={quantityUpdating || cartQtyForSelected <= 0}
              onClick={async () => {
                if (!item || cartQtyForSelected <= 0) return;
                if (!requireWebLogin()) return;
                setAddToCartError(null);
                setQuantityUpdating(true);
                try {
                  await setCartQuantityByItem(item.id, selectedSize || null, cartQtyForSelected - 1);
                  await refreshItem();
                } catch (e) {
                  setAddToCartError(e?.message || 'Ошибка');
                } finally {
                  setQuantityUpdating(false);
                }
              }}
            >
              −
            </button>
            <input
              type="number"
              min={0}
              value={showQuantityControls ? cartInputQty : cartQtyForSelected}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                setCartInputQty(Number.isNaN(v) || v < 0 ? 0 : v);
              }}
              onBlur={() => {
                if (!requireWebLogin()) return;
                const v = Math.max(0, cartInputQty);
                if (v === cartQtyForSelected) return;
                setAddToCartError(null);
                setQuantityUpdating(true);
                setCartQuantityByItem(item.id, selectedSize || null, v)
                  .then(() => refreshItem())
                  .catch((err) => setAddToCartError(err?.message || 'Ошибка'))
                  .finally(() => setQuantityUpdating(false));
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.target.blur();
              }}
              className="item-page__cart-qty-input"
              aria-label="Количество в корзине"
              disabled={quantityUpdating}
            />
            <button
              type="button"
              className="item-page__cart-qty-btn"
              aria-label="Увеличить количество"
              disabled={quantityUpdating}
              onClick={async () => {
                if (!item) return;
                if (!requireWebLogin()) return;
                setAddToCartError(null);
                setQuantityUpdating(true);
                try {
                  await addToCart(item.id, selectedSize || null, 1);
                  track('product_add_to_cart', { item_id: item.id, source: entrySource, mode: 'increment' });
                  await refreshItem();
                } catch (e) {
                  setAddToCartError(e?.message || 'Ошибка');
                  if (e?.status === 401) setAddToCartError('Войдите в аккаунт');
                } finally {
                  setQuantityUpdating(false);
                }
              }}
            >
              +
            </button>
          </div>
        ) : (
          <Button
            size="large"
            variant="primary"
            className="item-page__add-to-cart-btn"
            disabled={addToCartLoading || !item}
            onClick={async () => {
              if (!item) return;
              if (!requireWebLogin()) return;
              if (sizes.length > 0 && (selectedSize == null || selectedSize === '')) {
                setAddToCartError('Выберите размер');
                return;
              }
              setAddToCartError(null);
              setAddToCartLoading(true);
              try {
                await addToCart(item.id, selectedSize || null, 1);
                track('product_add_to_cart', { item_id: item.id, source: entrySource, mode: 'button' });
                await refreshItem();
                if (isTelegramWebAppEnvironment() && window.Telegram?.WebApp?.showPopup) {
                  window.Telegram.WebApp.showPopup({ title: 'В корзину', message: 'Товар добавлен в корзину' });
                }
              } catch (e) {
                const msg = e?.message || 'Не удалось добавить в корзину';
                setAddToCartError(msg);
                if (e?.status === 401) {
                  setAddToCartError('Войдите в аккаунт, чтобы добавить товар в корзину');
                }
              } finally {
                setAddToCartLoading(false);
              }
            }}
          >
            {addToCartLoading ? 'Добавление…' : 'В корзину'}
          </Button>
        )}
      </div>
    </div>
  );
}

function PriceHistoryModal({ onClose, history }) {
  const hasData = Array.isArray(history) && history.length > 0;

  let points = [];
  let globalMin = null;
  let globalMax = null;

  if (hasData) {
    points = history
      .map((point, index) => {
        const min = Number(point.min_price);
        const max = Number(point.max_price);
        const avg = point.avg_price != null ? Number(point.avg_price) : null;
        const value = Number.isFinite(avg) ? avg : (Number.isFinite(min) && Number.isFinite(max) ? (min + max) / 2 : null);
        const date = point.week_start ? new Date(point.week_start) : null;
        return { index, min, max, value, date };
      })
      .filter((p) => p.value != null && p.date instanceof Date && !Number.isNaN(p.date.getTime()));

    if (points.length > 0) {
      globalMin = points.reduce((acc, p) => (acc == null || p.value < acc ? p.value : acc), null);
      globalMax = points.reduce((acc, p) => (acc == null || p.value > acc ? p.value : acc), null);
    }
  }

  const width = 260;
  const height = 140;
  const paddingTop = 10;
  const paddingBottom = 10;
  const usableHeight = height - paddingTop - paddingBottom;

  const [hoverIndex, setHoverIndex] = useState(points.length > 0 ? points.length - 1 : null);

  let pathD = '';
  const xPositions = [];

  if (points.length > 1 && globalMin != null && globalMax != null && globalMax !== globalMin) {
    const xStep = width / (points.length - 1);
    pathD = points
      .map((p, idx) => {
        const x = idx * xStep;
        xPositions[idx] = x;
        const t = (p.value - globalMin) / (globalMax - globalMin || 1);
        const y = paddingTop + (1 - t) * usableHeight;
        return `${idx === 0 ? 'M' : 'L'} ${x} ${y}`;
      })
      .join(' ');
  }

  const formatDate = (date) => {
    if (!(date instanceof Date)) return '';
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  };

  const activeIndex = hoverIndex != null && points[hoverIndex] ? hoverIndex : (points.length > 0 ? points.length - 1 : null);
  const activePoint = activeIndex != null ? points[activeIndex] : null;

  const handlePointerMove = (event) => {
    if (points.length === 0 || xPositions.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const xRel = event.clientX - rect.left;
    if (xRel < 0 || xRel > rect.width) return;
    const t = xRel / rect.width;
    const idx = Math.round(t * (points.length - 1));
    if (idx >= 0 && idx < points.length) {
      setHoverIndex(idx);
    }
  };

  return (
    <div className="item-page__history-backdrop" onClick={onClose}>
      <div
        className="item-page__history-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="item-page__history-header">
          <span className="item-page__history-title">История цен</span>
          <button type="button" className="item-page__history-close" onClick={onClose}>
            ✕
          </button>
        </div>
        {points.length > 1 && pathD ? (
          <div
            className="item-page__history-chart-wrapper"
            onPointerDown={handlePointerMove}
            onPointerMove={handlePointerMove}
          >
            <svg
              className="item-page__history-chart"
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label="График изменения цены"
            >
              <line x1="0" y1={height - paddingBottom} x2={width} y2={height - paddingBottom} stroke="rgba(0,0,0,0.2)" strokeWidth="1" />
              <line x1="10" y1="0" x2="10" y2={height} stroke="rgba(0,0,0,0.2)" strokeWidth="1" />
              <path d={pathD} fill="none" stroke="var(--accent-primary, #2ecc71)" strokeWidth="2" />
              {globalMin != null && globalMax != null && (
                <>
                  <text
                    x="14"
                    y={paddingTop + 6}
                    fontFamily="var(--font-family)"
                    fontSize="10"
                    fill="rgba(0,0,0,0.6)"
                  >
                    {formatRublesForUser(globalMax)}
                  </text>
                  <text
                    x="14"
                    y={height - paddingBottom - 2}
                    fontFamily="var(--font-family)"
                    fontSize="10"
                    fill="rgba(0,0,0,0.6)"
                  >
                    {formatRublesForUser(globalMin)}
                  </text>
                </>
              )}
              {activePoint && globalMin != null && globalMax != null && globalMax !== globalMin && (
                (() => {
                  const idx = activePoint.index;
                  const x = xPositions[idx] != null ? xPositions[idx] : 0;
                  const t = (activePoint.value - globalMin) / (globalMax - globalMin || 1);
                  const y = paddingTop + (1 - t) * usableHeight;
                  return (
                    <>
                      <line
                        x1={x}
                        y1={paddingTop}
                        x2={x}
                        y2={height - paddingBottom}
                        stroke="rgba(0,0,0,0.25)"
                        strokeWidth="1"
                        strokeDasharray="4 3"
                      />
                      <circle
                        cx={x}
                        cy={y}
                        r="4"
                        fill="var(--accent-primary, #2ecc71)"
                        stroke="#ffffff"
                        strokeWidth="1"
                      />
                    </>
                  );
                })()
              )}
            </svg>
            <div className="item-page__history-x-labels">
              {points.map((p) => (
                <span
                  key={p.index}
                  className={`item-page__history-x-label ${activeIndex === p.index ? 'item-page__history-x-label--active' : ''}`.trim()}
                >
                  {formatDate(p.date)}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="item-page__history-empty">Недостаточно данных для графика</div>
        )}
        {globalMin != null && globalMax != null && (
          <div className="item-page__history-footer">
            <div className="item-page__history-stat">
              <span className="item-page__history-stat-label">Минимум</span>
              <span className="item-page__history-stat-value">{formatRublesForUser(globalMin)}</span>
            </div>
            <div className="item-page__history-stat">
              <span className="item-page__history-stat-label">Максимум</span>
              <span className="item-page__history-stat-value">{formatRublesForUser(globalMax)}</span>
            </div>
          </div>
        )}
        {activePoint && (
          <div className="item-page__history-active">
            <span className="item-page__history-active-date">{formatDate(activePoint.date)}</span>
            <span className="item-page__history-active-value">{formatRublesForUser(activePoint.value)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function SizeChartModal({ onClose, sizeChart }) {
  const rows = sizeChart?.grid?.rows ?? [];
  return (
    <div className="item-page__history-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Размерная сетка">
      <div
        className="item-page__history-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="item-page__history-header">
          <h2 className="item-page__history-title">
            {sizeChart?.name || 'Размерная сетка'}
          </h2>
          <button type="button" className="item-page__history-close" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        <div className="item-page__size-chart-content">
          {rows.length > 0 ? (
            <table className="item-page__size-chart-table">
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="item-page__size-chart-cell">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="item-page__history-empty">Нет данных</p>
          )}
        </div>
      </div>
    </div>
  );
}

