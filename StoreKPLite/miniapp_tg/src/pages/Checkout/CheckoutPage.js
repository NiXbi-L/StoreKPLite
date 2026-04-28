import React, { useEffect, useState, useMemo, useRef } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import {
  getCartItems,
  getCartParcel,
  checkoutCreateOrder,
  checkoutPreviewOrder,
  createOrderPayment,
  getStoredCheckoutPromo,
  setStoredCheckoutPromo,
} from '../../api/products';
import { getUserDeliveryPresets, getDeliveryMethods, calculateDeliveryCost } from '../../api/delivery';
import Button from '../../components/Button';
import { openYookassaConfirmationUrl } from '../../utils/openYookassaPayment';
import { startOrderPaymentPolling } from '../../utils/paymentReturnPolling';
import { formatRublesForUser } from '../../utils/formatRubles';
import { track } from '../../utils/productAnalytics';
import {
  SHOW_ORDER_CHECKOUT_PAUSE_BANNER,
  ORDER_CHECKOUT_PAUSE_TG_URL,
  orderCheckoutPauseBannerTextBeforeLink,
  orderCheckoutPausePlainErrorText,
} from '../../constants/checkoutPauseNotice';
import './CheckoutPage.css';

const SVG_CHEVRON_RIGHT = (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function getItemPrice(cartItem) {
  const item = cartItem?.item || {};
  const fixed = item.fixed_price_rub != null ? Number(item.fixed_price_rub) : null;
  if (Number.isFinite(fixed)) return fixed;
  const p = cartItem.price_rub != null ? Number(cartItem.price_rub) : Number(item.price_rub);
  return Number.isFinite(p) ? p : 0;
}

function getStockTypeLabel(stockType, item) {
  const hasFixed = item?.fixed_price_rub != null && Number.isFinite(Number(item.fixed_price_rub));
  if (hasFixed) return stockType === 'in_stock' ? 'Наличие' : 'Под заказ';
  return 'Под заказ';
}

export default function CheckoutPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTabBarVisible } = useTabBarVisibility();
  const selectedCartItemIds = location.state?.selectedCartItemIds ?? null;
  const selectedDeliveryPresetFromState = location.state?.selectedDeliveryPreset ?? null;
  const [allCartItems, setAllCartItems] = useState([]);
  const [presets, setPresets] = useState([]);
  const [deliveryMethods, setDeliveryMethods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deliveryCostRub, setDeliveryCostRub] = useState(null);
  const [deliveryCostLoading, setDeliveryCostLoading] = useState(false);
  const [payLoading, setPayLoading] = useState(false);
  const [checkoutPreview, setCheckoutPreview] = useState(null);
  const [promoCode, setPromoCode] = useState(() => getStoredCheckoutPromo());
  const [promoPreviewError, setPromoPreviewError] = useState(null);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const checkoutOrderPollRef = useRef(null);
  const checkoutSessionIdRef = useRef(
    typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `c${Date.now()}`
  );
  const checkoutEnteredAtRef = useRef(Date.now());
  const checkoutLastStageRef = useRef('loading');

  const deliveryPreset = selectedDeliveryPresetFromState ?? (presets.length > 0 ? (presets.find((p) => p.is_default) || presets[0]) : null);
  const deliveryMethod = deliveryPreset && deliveryMethods.length > 0
    ? deliveryMethods.find((m) => m.id === deliveryPreset.delivery_method_id)
    : null;
  const deliveryMethodName = deliveryMethod?.name || 'Доставка';
  const deliveryAddress = deliveryPreset?.address?.trim() || '';

  const items = useMemo(() => {
    if (!Array.isArray(selectedCartItemIds) || selectedCartItemIds.length === 0) {
      return [];
    }
    const idSet = new Set(selectedCartItemIds);
    return allCartItems.filter((it) => idSet.has(it.id));
  }, [allCartItems, selectedCartItemIds]);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) {
      return () => setTabBarVisible(true);
    }
    const handleBack = () => navigate(-1);
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
      setTabBarVisible(true);
    };
  }, [navigate, setTabBarVisible]);

  useEffect(() => {
    const threshold = 80;
    const baseHeight = window.innerHeight;

    const handleResize = () => {
      const currentHeight = window.innerHeight;
      setKeyboardOpen(baseHeight - currentHeight > threshold);
    };

    window.addEventListener('resize', handleResize);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', handleResize);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener('resize', handleResize);
      }
    };
  }, []);

  useEffect(() => {
    return () => {
      checkoutOrderPollRef.current?.();
      checkoutOrderPollRef.current = null;
    };
  }, []);

  useEffect(() => {
    track('checkout_enter', {
      checkout_session_id: checkoutSessionIdRef.current,
      cart_items_count: Array.isArray(selectedCartItemIds) ? selectedCartItemIds.length : 0,
      has_delivery_preset: Boolean(selectedDeliveryPresetFromState),
    });
    return () => {
      track('checkout_leave', {
        checkout_session_id: checkoutSessionIdRef.current,
        dwell_ms: Date.now() - checkoutEnteredAtRef.current,
        last_stage: checkoutLastStageRef.current,
      });
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadStarted = Date.now();
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [cartData, presetsData, methodsData] = await Promise.all([
          getCartItems(),
          getUserDeliveryPresets().catch(() => []),
          getDeliveryMethods().catch(() => []),
        ]);
        if (!cancelled) {
          setAllCartItems(Array.isArray(cartData) ? cartData : []);
          setPresets(Array.isArray(presetsData) ? presetsData : []);
          setDeliveryMethods(Array.isArray(methodsData) ? methodsData : []);
          track('checkout_loaded', {
            checkout_session_id: checkoutSessionIdRef.current,
            duration_ms: Date.now() - loadStarted,
            ok: true,
            cart_lines: Array.isArray(cartData) ? cartData.length : 0,
            presets_count: Array.isArray(presetsData) ? presetsData.length : 0,
            methods_count: Array.isArray(methodsData) ? methodsData.length : 0,
          });
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Не удалось загрузить данные');
          setAllCartItems([]);
          track('checkout_loaded', {
            checkout_session_id: checkoutSessionIdRef.current,
            duration_ms: Date.now() - loadStarted,
            ok: false,
            message: String(e?.message || e || '').slice(0, 200),
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (loading) {
      checkoutLastStageRef.current = 'loading';
      return;
    }
    if (error) {
      checkoutLastStageRef.current = 'error';
      return;
    }
    if (!Array.isArray(selectedCartItemIds) || selectedCartItemIds.length === 0) {
      checkoutLastStageRef.current = 'empty_cart';
      return;
    }
    checkoutLastStageRef.current = payLoading ? 'paying' : 'ready';
  }, [loading, error, selectedCartItemIds, payLoading]);

  useEffect(() => {
    if (!deliveryPreset || !deliveryMethod || !Array.isArray(selectedCartItemIds) || selectedCartItemIds.length === 0) {
      setDeliveryCostRub(null);
      return;
    }
    let cancelled = false;
    setDeliveryCostLoading(true);
    (async () => {
      try {
        const parcel = await getCartParcel(selectedCartItemIds);
        if (cancelled) return;
        const goodsSubtotal = items.reduce((s, cartItem) => {
          const pricePerUnit = getItemPrice(cartItem);
          const qty = cartItem.quantity || 1;
          return s + pricePerUnit * qty;
        }, 0);
        const cdekExtras =
          deliveryMethod.code === 'CDEK' && goodsSubtotal > 0
            ? { cdek_declared_value_rub: goodsSubtotal }
            : null;
        const result = await calculateDeliveryCost(
          parcel,
          deliveryMethod.code,
          deliveryMethod.code === 'CDEK' || deliveryMethod.code === 'CDEK_MANUAL'
            ? deliveryAddress || undefined
            : undefined,
          cdekExtras
        );
        if (!cancelled) setDeliveryCostRub(result.delivery_cost_rub != null ? result.delivery_cost_rub : null);
      } catch (e) {
        if (!cancelled) setDeliveryCostRub(null);
      } finally {
        if (!cancelled) setDeliveryCostLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [deliveryPreset?.id, deliveryMethod?.code, deliveryAddress, items]);

  const totalPrice = useMemo(() => {
    return items.reduce((sum, cartItem) => {
      const pricePerUnit = getItemPrice(cartItem);
      const qty = cartItem.quantity || 1;
      return sum + pricePerUnit * qty;
    }, 0);
  }, [items]);

  const previewDeliveryRub =
    checkoutPreview != null && checkoutPreview.delivery_cost_rub != null
      ? Number(checkoutPreview.delivery_cost_rub)
      : null;
  const shownDeliveryCostRub = Number.isFinite(previewDeliveryRub)
    ? previewDeliveryRub
    : Number.isFinite(deliveryCostRub)
      ? deliveryCostRub
      : null;

  const estimatedTotalToPay = totalPrice + (Number.isFinite(shownDeliveryCostRub) ? shownDeliveryCostRub : 0);
  const previewPromoDiscount = Number(checkoutPreview?.promo_discount_rub || 0);
  const previewPayable = Number(checkoutPreview?.payable_total_rub || 0);
  const previewOwnerWaiver = Boolean(checkoutPreview?.owner_waiver);
  const totalToPay = checkoutPreview ? previewPayable : estimatedTotalToPay;

  useEffect(() => {
    // При изменении состава/доставки пересчитываем preview скидок и суммы.
    if (!Array.isArray(selectedCartItemIds) || selectedCartItemIds.length === 0 || !deliveryPreset) {
      setCheckoutPreview(null);
      setPromoPreviewError(null);
      return;
    }
    if (SHOW_ORDER_CHECKOUT_PAUSE_BANNER) {
      setCheckoutPreview(null);
      setPromoPreviewError(null);
      return;
    }
    let cancelled = false;
    // Доставку и контакт для снимка заказа подтягивает products с delivery-service по id пресета.
    const basePayload =
      deliveryPreset?.id != null
        ? { cart_item_ids: selectedCartItemIds, delivery_preset_id: deliveryPreset.id }
        : {
            cart_item_ids: selectedCartItemIds,
            recipient_name: deliveryPreset?.recipient_name ?? undefined,
            phone_number: deliveryPreset?.phone_number ?? undefined,
            delivery_address: deliveryPreset?.address?.trim() || undefined,
            delivery_postal_code: deliveryPreset?.postal_code?.trim() || undefined,
            delivery_city_code: deliveryPreset?.city_code != null ? Number(deliveryPreset.city_code) : undefined,
            delivery_method_code: deliveryMethod?.code?.trim() || undefined,
            cdek_delivery_point_code: deliveryPreset?.cdek_delivery_point_code?.trim() || undefined,
          };
    (async () => {
      const trimmedPromo = (promoCode || '').trim();
      try {
        const prev = await checkoutPreviewOrder({
          ...basePayload,
          ...(trimmedPromo ? { promo_code: trimmedPromo } : {}),
        });
        if (!cancelled) {
          setPromoPreviewError(null);
          setCheckoutPreview(prev);
          setError(null);
        }
      } catch (e) {
        if (e?.checkoutDisabled) {
          if (!cancelled) {
            setCheckoutPreview(null);
            setPromoPreviewError(null);
            setError(orderCheckoutPausePlainErrorText());
          }
          return;
        }
        if (!trimmedPromo) {
          if (!cancelled) {
            setCheckoutPreview(null);
            setPromoPreviewError(null);
          }
          return;
        }
        try {
          const prev = await checkoutPreviewOrder(basePayload);
          if (!cancelled) {
            setCheckoutPreview(prev);
            setPromoPreviewError(
              typeof e?.message === 'string' && e.message.trim()
                ? e.message.trim()
                : 'Промокод не применился',
            );
          }
        } catch (e2) {
          if (e2?.checkoutDisabled) {
            if (!cancelled) {
              setCheckoutPreview(null);
              setPromoPreviewError(null);
              setError(orderCheckoutPausePlainErrorText());
            }
            return;
          }
          if (!cancelled) {
            setCheckoutPreview(null);
            setPromoPreviewError(null);
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCartItemIds?.join(','), deliveryPreset?.id, deliveryMethod?.code, deliveryAddress, promoCode]);

  const handlePay = async () => {
    if (SHOW_ORDER_CHECKOUT_PAUSE_BANNER) {
      return;
    }
    if (!Array.isArray(selectedCartItemIds) || selectedCartItemIds.length === 0) {
      setError('Выберите товары для заказа');
      return;
    }
    track('checkout_pay_click', {
      checkout_session_id: checkoutSessionIdRef.current,
      has_delivery_preset: Boolean(deliveryPreset),
      delivery_method_code: deliveryMethod?.code || null,
      cart_items_count: selectedCartItemIds.length,
    });
    setPayLoading(true);
    setError(null);
    try {
      const trimmedPromo = (promoCode || '').trim();
      const checkoutPayload =
        deliveryPreset?.id != null
          ? { cart_item_ids: selectedCartItemIds, delivery_preset_id: deliveryPreset.id }
          : {
              cart_item_ids: selectedCartItemIds,
              recipient_name: deliveryPreset?.recipient_name ?? undefined,
              phone_number: deliveryPreset?.phone_number ?? undefined,
              delivery_address: deliveryPreset?.address?.trim() || undefined,
              delivery_postal_code: deliveryPreset?.postal_code?.trim() || undefined,
              delivery_city_code: deliveryPreset?.city_code != null ? Number(deliveryPreset.city_code) : undefined,
              delivery_method_code: deliveryMethod?.code?.trim() || undefined,
              cdek_delivery_point_code: deliveryPreset?.cdek_delivery_point_code?.trim() || undefined,
            };
      const prepared = await checkoutCreateOrder({
        ...checkoutPayload,
        ...(trimmedPromo ? { promo_code: trimmedPromo } : {}),
      });
      const returnUrl =
        typeof window !== 'undefined'
          ? `${window.location.origin}${window.location.pathname || '/'}#/main/cart`
          : '';
      const payResult = await createOrderPayment(prepared.order_id, returnUrl);
      if (payResult.owner_payment_skipped) {
        track('checkout_pay_owner_skipped', {
          checkout_session_id: checkoutSessionIdRef.current,
          order_id: prepared.order_id,
        });
        window.dispatchEvent(new CustomEvent('miniapp-invalidate-cart'));
        getCartItems()
          .then((cartData) => setAllCartItems(Array.isArray(cartData) ? cartData : []))
          .catch(() => {});
        navigate('/main/cart', { replace: true });
        return;
      }
      if (payResult.confirmation_url) {
        checkoutOrderPollRef.current?.();
        checkoutOrderPollRef.current = startOrderPaymentPolling({
          orderId: prepared.order_id,
          expectedTotalRub: prepared.payable_total_rub,
          onTick: async () => {
            try {
              const cartData = await getCartItems();
              setAllCartItems(Array.isArray(cartData) ? cartData : []);
            } catch {
              /* ignore */
            }
          },
          onPaid: () => {
            checkoutOrderPollRef.current = null;
            window.dispatchEvent(new CustomEvent('miniapp-invalidate-cart'));
            getCartItems()
              .then((cartData) => setAllCartItems(Array.isArray(cartData) ? cartData : []))
              .catch(() => {});
            // WebView миниаппа остаётся на /checkout, пока пользователь платит во внешнем браузере — уводим на корзину.
            navigate('/main/cart', { replace: true });
          },
        });
        track('checkout_pay_redirect', {
          checkout_session_id: checkoutSessionIdRef.current,
          order_id: prepared.order_id,
        });
        openYookassaConfirmationUrl(payResult.confirmation_url);
        return;
      }
      setError('Не получена ссылка на оплату');
      track('checkout_pay_error', {
        checkout_session_id: checkoutSessionIdRef.current,
        reason: 'no_confirmation_url',
      });
    } catch (e) {
      setError(e?.message || 'Ошибка при создании заказа или платежа');
      track('checkout_pay_error', {
        checkout_session_id: checkoutSessionIdRef.current,
        reason: 'exception',
        message: String(e?.message || e || '').slice(0, 200),
      });
    } finally {
      setPayLoading(false);
    }
  };

  const showFixedPayBar =
    !loading && !error && items.length > 0 && !SHOW_ORDER_CHECKOUT_PAUSE_BANNER;
  const showPayBarVisible = showFixedPayBar && !keyboardOpen;

  const checkoutPauseApiError =
    typeof error === 'string' && error.includes(ORDER_CHECKOUT_PAUSE_TG_URL);
  const showCheckoutComposition =
    !loading &&
    items.length > 0 &&
    (!error || SHOW_ORDER_CHECKOUT_PAUSE_BANNER || checkoutPauseApiError);

  return (
    <div
      className={`checkout-page${showPayBarVisible ? ' checkout-page--with-fixed-pay' : ''}`}
    >
      <div className="checkout-page__header">
        <div className="checkout-page__header-text">Оформление заказа</div>
      </div>

      {loading && <p className="checkout-page__status">Загрузка…</p>}
      {SHOW_ORDER_CHECKOUT_PAUSE_BANNER && !loading && (
        <p className="checkout-page__status checkout-page__status--error" role="status">
          {orderCheckoutPauseBannerTextBeforeLink()}{' '}
          <a
            href={ORDER_CHECKOUT_PAUSE_TG_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="checkout-page__offer-link"
          >
            t.me/MatchWear_chine
          </a>
        </p>
      )}
      {error && !loading && (
        <p className="checkout-page__status checkout-page__status--error" role="alert">
          {typeof error === 'string' && error.includes(ORDER_CHECKOUT_PAUSE_TG_URL) ? (
            <>
              {orderCheckoutPauseBannerTextBeforeLink()}{' '}
              <a
                href={ORDER_CHECKOUT_PAUSE_TG_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="checkout-page__offer-link"
              >
                t.me/MatchWear_chine
              </a>
            </>
          ) : (
            error
          )}
        </p>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="checkout-page__status">
          Нет выбранных товаров. Выберите товары в корзине и перейдите к оформлению.
        </p>
      )}
      {showCheckoutComposition && (
        <div className="checkout-page__composition">
          <div className="checkout-page__composition-items">
            {items.map((cartItem) => {
              const item = cartItem.item || {};
              const name = item.name || 'Товар';
              const size = (cartItem.size || '').trim() || '—';
              const stockLabel = getStockTypeLabel(cartItem.stock_type, item);
              const pricePerUnit = getItemPrice(cartItem);
              const qty = cartItem.quantity || 1;
              const imageSrc = item?.photo ? `/${item.photo}` : null;
              const titleText = `${name} | ${size} | ${stockLabel}`;

              return (
                <div key={cartItem.id} className="checkout-page__composition-row">
                  <div className="checkout-page__composition-photo">
                    {imageSrc ? (
                      <img src={imageSrc} alt="" className="checkout-page__composition-photo-img" />
                    ) : (
                      <div className="checkout-page__composition-photo-placeholder" />
                    )}
                  </div>
                  <div className="checkout-page__composition-title-wrap">
                    <span className="checkout-page__composition-title-text" title={titleText}>
                      {titleText}
                    </span>
                  </div>
                  <div className="checkout-page__composition-price-wrap">
                    <span className="checkout-page__composition-price-text">
                      {qty} * {formatRublesForUser(pricePerUnit)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="checkout-page__composition-total">
            <span className="checkout-page__composition-total-label">Итого:</span>
            <span className="checkout-page__composition-total-value">{formatRublesForUser(totalPrice)}</span>
          </div>
          {checkoutPreview && previewPromoDiscount > 0 && (
            <div className="checkout-page__composition-total">
              <span className="checkout-page__composition-total-label">Скидка по промокоду:</span>
              <span className="checkout-page__composition-total-value">−{formatRublesForUser(previewPromoDiscount)}</span>
            </div>
          )}
          {checkoutPreview && previewOwnerWaiver && (
            <div className="checkout-page__composition-total">
              <span className="checkout-page__composition-total-label">Скидка владельца:</span>
              <span className="checkout-page__composition-total-value">100%</span>
            </div>
          )}
          {checkoutPreview && (
            <div className="checkout-page__composition-total checkout-page__composition-total--strong">
              <span className="checkout-page__composition-total-label">К оплате:</span>
              <span className="checkout-page__composition-total-value">{formatRublesForUser(previewPayable)}</span>
            </div>
          )}
        </div>
      )}

      {showCheckoutComposition && (
        <div className="checkout-page__delivery">
          <p className="checkout-page__delivery-label">Способ доставки:</p>
          <button
            type="button"
            className="checkout-page__delivery-btn"
            onClick={() => {
              track('checkout_choose_delivery_click', {
                checkout_session_id: checkoutSessionIdRef.current,
              });
              navigate('/main/profile/addresses', {
                state: { fromCheckout: true, selectedCartItemIds },
              });
            }}
          >
            <div className="checkout-page__delivery-btn-row">
              <span className="checkout-page__delivery-method-name">
                {deliveryPreset ? deliveryMethodName || 'Доставка' : 'Выберите способ доставки'}
              </span>
              {deliveryAddress ? (
                <span className="checkout-page__delivery-address" title={deliveryAddress}>
                  {deliveryAddress.length > 60 ? `, ${deliveryAddress.slice(0, 57)}...` : `, ${deliveryAddress}`}
                </span>
              ) : deliveryPreset && !deliveryAddress ? (
                <span className="checkout-page__delivery-address">, Адрес не указан</span>
              ) : null}
              <span className="checkout-page__delivery-arrow">{SVG_CHEVRON_RIGHT}</span>
            </div>
          </button>
          {(deliveryCostLoading || shownDeliveryCostRub != null) && (
            <p className="checkout-page__delivery-cost">
              {deliveryCostLoading && !Number.isFinite(shownDeliveryCostRub)
                ? 'Стоимость доставки: …'
                : Number.isFinite(shownDeliveryCostRub)
                  ? `Стоимость доставки: ${formatRublesForUser(shownDeliveryCostRub)}`
                  : 'Стоимость доставки: —'}
            </p>
          )}
          {deliveryPreset && deliveryMethod?.code === 'CDEK_MANUAL' ? (
            <p className="checkout-page__cdek-manual-notice" role="status">
              Стоимость доставки по этому способу сразу не рассчитывается. После оплаты с вами свяжется менеджер,
              чтобы согласовать доставку и её стоимость. Если условия вас не устроят — заказ отменим.
            </p>
          ) : null}
          <div className="checkout-page__promo">
            <label className="checkout-page__promo-label" htmlFor="checkout-promo-input">
              Промокод
            </label>
            <input
              id="checkout-promo-input"
              className="checkout-page__promo-input"
              type="text"
              autoCapitalize="characters"
              autoComplete="off"
              placeholder="Код"
              value={promoCode}
              onChange={(e) => {
                const v = e.target.value;
                setPromoCode(v);
                setStoredCheckoutPromo(v);
              }}
            />
            {promoPreviewError ? (
              <p className="checkout-page__promo-error" role="alert">
                {promoPreviewError}
              </p>
            ) : null}
          </div>
        </div>
      )}

      {showFixedPayBar && (
        <div className={`checkout-page__pay${keyboardOpen ? ' checkout-page__pay--hidden' : ''}`}>
          <Button
            type="button"
            size="small"
            variant="primary"
            loading={payLoading}
            disabled={payLoading || !deliveryPreset}
            onClick={handlePay}
            className="checkout-page__pay-btn"
          >
            Оплатить {formatRublesForUser(totalToPay)}
          </Button>
          <p className="checkout-page__hint">
            Оплачивая заказ, вы соглашаетесь с договором{' '}
            <Link to="/public-offer" className="checkout-page__offer-link">
              публичной оферты
            </Link>
            . Сумма к оплате учитывает промокод (если введён).
          </p>
        </div>
      )}
    </div>
  );
}
