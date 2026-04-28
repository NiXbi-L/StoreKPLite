import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { getOrders, hideOrder, cancelOrder, createOrderPayment } from '../../api/products';
import { openYookassaConfirmationUrl } from '../../utils/openYookassaPayment';
import { startOrderPaymentPolling } from '../../utils/paymentReturnPolling';
import Button from '../../components/Button';
import { formatRublesForUser } from '../../utils/formatRubles';
import { clearStartappItemRoot } from '../../utils/startappItemEntry';
import { track } from '../../utils/productAnalytics';
import './OrdersPage.css';

const STATUS_BADGE_COLORS = {
  'Ожидает': '#e5c456',
  'Выкуп': '#9b56e5',
  'в работе': '#565de5',
  'В работе': '#565de5',
  'Собран': '#56e57c',
  'отменен': '#e56256',
  'Отменен': '#e56256',
  'завершен': '#56e567',
  'Завершен': '#56e567',
};

function getStockLabel(stockType) {
  return stockType === 'in_stock' ? 'Наличие' : 'Под заказ';
}

function formatOrderDate(createdAt) {
  if (!createdAt) return '';
  try {
    const d = new Date(createdAt);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return '';
  }
}

const SVG_TRASH = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path
      d="M20.25 4.5H16.5V3.75C16.5 3.15326 16.2629 2.58097 15.841 2.15901C15.419 1.73705 14.8467 1.5 14.25 1.5H9.75C9.15326 1.5 8.58097 1.73705 8.15901 2.15901C7.73705 2.58097 7.5 3.15326 7.5 3.75V4.5H3.75C3.55109 4.5 3.36032 4.57902 3.21967 4.71967C3.07902 4.86032 3 5.05109 3 5.25C3 5.44891 3.07902 5.63968 3.21967 5.78033C3.36032 5.92098 3.55109 6 3.75 6H4.5V19.5C4.5 19.8978 4.65804 20.2794 4.93934 20.5607C5.22064 20.842 5.60218 21 6 21H18C18.3978 21 18.7794 20.842 19.0607 20.5607C19.342 20.2794 19.5 19.8978 19.5 19.5V6H20.25C20.4489 6 20.6397 5.92098 20.7803 5.78033C20.921 5.63968 21 5.44891 21 5.25C21 5.05109 20.921 4.86032 20.7803 4.71967C20.6397 4.57902 20.4489 4.5 20.25 4.5ZM9 3.75C9 3.55109 9.07902 3.36032 9.21967 3.21967C9.36032 3.07902 9.55109 3 9.75 3H14.25C14.4489 3 14.6397 3.07902 14.7803 3.21967C14.921 3.36032 15 3.55109 15 3.75V4.5H9V3.75ZM18 19.5H6V6H18V19.5ZM10.5 9.75V15.75C10.5 15.9489 10.421 16.1397 10.2803 16.2803C10.1397 16.421 9.94891 16.5 9.75 16.5C9.55109 16.5 9.36032 16.421 9.21967 16.2803C9.07902 16.1397 9 15.9489 9 15.75V9.75C9 9.55109 9.07902 9.36032 9.21967 9.21967C9.36032 9.07902 9.55109 9 9.75 9C9.94891 9 10.1397 9.07902 10.2803 9.21967C10.421 9.36032 10.5 9.55109 10.5 9.75ZM15 9.75V15.75C15 15.9489 14.921 16.1397 14.7803 16.2803C14.6397 16.421 14.4489 16.5 14.25 16.5C14.0511 16.5 13.8603 16.421 13.7197 16.2803C13.579 16.1397 13.5 15.9489 13.5 15.75V9.75C13.5 9.55109 13.579 9.36032 13.7197 9.21967C13.8603 9.07902 14.0511 9 14.25 9C14.4489 9 14.6397 9.07902 14.7803 9.21967C14.921 9.36032 15 9.55109 15 9.75Z"
      fill="#525252"
    />
  </svg>
);

const CDEK_TRACK_URL = 'https://www.cdek.ru/track?order_id=';

function DeliveryTrackingModal({ onClose, order }) {
  const trackingNumber = order?.tracking_number?.trim() || null;
  const deliveryStatus = order?.delivery?.status_name || null;
  const [copied, setCopied] = useState(false);

  const trackUrl = trackingNumber ? `${CDEK_TRACK_URL}${encodeURIComponent(trackingNumber)}` : null;

  const handleCopy = useCallback(() => {
    if (!trackingNumber) return;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(trackingNumber).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  }, [trackingNumber]);

  const handleOpenTrack = useCallback(() => {
    if (!trackUrl) return;
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) {
      tg.openLink(trackUrl);
    } else {
      window.open(trackUrl, '_blank', 'noopener,noreferrer');
    }
  }, [trackUrl]);

  return (
    <div
      className="orders-page__modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Трек доставки"
    >
      <div className="orders-page__modal" onClick={(e) => e.stopPropagation()}>
        <div className="orders-page__modal-header">
          <span className="orders-page__modal-title">Трек доставки</span>
          <button type="button" className="orders-page__modal-close" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        <div className="orders-page__modal-body">
          {trackingNumber ? (
            <>
              <p className="orders-page__modal-status">
                Трек-номер: <strong>{trackingNumber}</strong>
              </p>
              <button
                type="button"
                className="orders-page__modal-link"
                onClick={handleOpenTrack}
              >
                Отследить на сайте СДЭК
              </button>
              <button
                type="button"
                className="orders-page__modal-copy"
                onClick={handleCopy}
              >
                {copied ? 'Скопировано' : 'Скопировать трек-номер'}
              </button>
            </>
          ) : (
            <p className="orders-page__modal-status">
              {deliveryStatus || 'Статус доставки пока не обновлён.'}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function OrdersPage() {
  const navigate = useNavigate();
  const { setTabBarVisible } = useTabBarVisibility();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [trackingOrder, setTrackingOrder] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const orderPollStopRef = useRef(null);
  const ordersSessionIdRef = useRef(
    typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `o${Date.now()}`
  );
  const ordersEnteredAtRef = useRef(Date.now());
  const ordersDeepestStageRef = useRef('list');

  const loadOrders = useCallback(async (opts = {}) => {
    const silent = opts.silent === true;
    try {
      if (!silent) {
        setLoading(true);
        setError(null);
      }
      const list = await getOrders();
      const arr = Array.isArray(list) ? list : [];
      setOrders(arr);
      if (!silent) {
        track('orders_list_loaded', {
          orders_session_id: ordersSessionIdRef.current,
          order_count: arr.length,
          ok: true,
        });
      }
    } catch (e) {
      if (!silent) {
        setError(e.message || 'Не удалось загрузить заказы');
        setOrders([]);
        track('orders_list_loaded', {
          orders_session_id: ordersSessionIdRef.current,
          order_count: 0,
          ok: false,
          message: String(e?.message || '').slice(0, 200),
        });
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

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
    track('orders_enter', { orders_session_id: ordersSessionIdRef.current });
    return () => {
      track('orders_leave', {
        orders_session_id: ordersSessionIdRef.current,
        dwell_ms: Date.now() - ordersEnteredAtRef.current,
        deepest_stage: ordersDeepestStageRef.current,
      });
    };
  }, []);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  useEffect(() => {
    return () => {
      orderPollStopRef.current?.();
      orderPollStopRef.current = null;
    };
  }, []);

  const handleHide = async (orderId) => {
    setActionLoading(orderId);
    try {
      await hideOrder(orderId);
      setOrders((prev) => prev.filter((o) => o.id !== orderId));
    } catch (e) {
      if (window.Telegram?.WebApp?.showAlert) {
        window.Telegram.WebApp.showAlert(e.message || 'Не удалось скрыть заказ');
      } else {
        alert(e.message || 'Не удалось скрыть заказ');
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (orderId) => {
    track('orders_cancel_click', { orders_session_id: ordersSessionIdRef.current, order_id: orderId });
    setActionLoading(orderId);
    try {
      await cancelOrder(orderId);
      setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, status: 'отменен' } : o)));
    } catch (e) {
      if (window.Telegram?.WebApp?.showAlert) {
        window.Telegram.WebApp.showAlert(e.message || 'Не удалось отменить заказ');
      } else {
        alert(e.message || 'Не удалось отменить заказ');
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handlePayRemainder = async (order) => {
    track('orders_pay_remainder_click', {
      orders_session_id: ordersSessionIdRef.current,
      order_id: order.id,
    });
    setActionLoading(order.id);
    try {
      const returnUrl = `${window.location.origin}${window.location.pathname || '/'}#/main/cart`;
      const payResult = await createOrderPayment(order.id, returnUrl);
      if (payResult.owner_payment_skipped) {
        loadOrders({ silent: true });
        return;
      }
      if (payResult.confirmation_url) {
        const grandTotal = order.order_total != null ? Number(order.order_total) : 0;
        orderPollStopRef.current?.();
        orderPollStopRef.current = startOrderPaymentPolling({
          orderId: order.id,
          expectedTotalRub: grandTotal,
          onTick: (o) => {
            setOrders((prev) => prev.map((x) => (x.id === o.id ? { ...x, ...o } : x)));
          },
          onPaid: () => {
            orderPollStopRef.current = null;
            loadOrders({ silent: true });
          },
        });
        openYookassaConfirmationUrl(payResult.confirmation_url);
        return;
      }
      throw new Error('Не получена ссылка на оплату');
    } catch (e) {
      if (window.Telegram?.WebApp?.showAlert) {
        window.Telegram.WebApp.showAlert(e.message || 'Ошибка оплаты');
      } else {
        alert(e.message || 'Ошибка оплаты');
      }
    } finally {
      setActionLoading(null);
    }
  };

  const statusDisplay = (s) => (s === 'в работе' ? 'В работе' : s === 'отменен' ? 'Отменен' : s === 'завершен' ? 'Завершен' : s);
  const canCancel = (s) => s === 'Ожидает' || s === 'Выкуп';
  const showTrack = (s) => s === 'в работе' || s === 'В работе' || s === 'Собран';
  const showTrash = (s) => s === 'отменен' || s === 'завершен';
  const showLeaveReview = (order) =>
    order?.status === 'завершен' && (order?.reviewable_item_ids?.length ?? 0) > 0;

  return (
    <div className="orders-page page-container">
      <div className="orders-page__header">
        <div className="orders-page__header-text">Мои заказы</div>
      </div>
      {loading && <p className="orders-page__status">Загрузка…</p>}
      {error && !loading && (
        <p className="orders-page__status orders-page__status--error" role="alert">
          {error}
        </p>
      )}
      {!loading && !error && orders.length === 0 && (
        <p className="orders-page__status">У вас пока нет заказов.</p>
      )}
      {!loading && !error && orders.length > 0 && (
        <div className="orders-page__list">
          {orders.map((order) => {
            const status = order.status || '';
            const badgeColor = STATUS_BADGE_COLORS[status] || STATUS_BADGE_COLORS[order.status === 'в работе' ? 'В работе' : status] || '#a3a3a3';
            const total = order.order_total != null ? Number(order.order_total) : 0;
            const paid = order.paid_amount != null ? Number(order.paid_amount) : 0;
            const snapshot = (order.order_data && order.order_data.delivery_snapshot) || {};
            const rawDeliveryCost = snapshot && snapshot.delivery_cost_rub != null ? Number(snapshot.delivery_cost_rub) : 0;
            const deliveryCost = Number.isFinite(rawDeliveryCost) && rawDeliveryCost > 0 ? rawDeliveryCost : 0;
            // order_total приходит с бэка как итог к оплате (товары - скидка + доставка)
            const grandTotal = total;
            const remainder = grandTotal - paid;
            const isCanceledOrCompleted = status === 'отменен' || status === 'завершен';
            const showRemainder = remainder > 0.01 && !isCanceledOrCompleted;
            const items = ((order.order_data && order.order_data.items) || []).filter((row) => !row.returned);

            return (
              <article key={order.id} className="order-card">
                <div className="order-card__top">
                  <span
                    className="order-card__badge"
                    style={{ background: badgeColor }}
                  >
                    {statusDisplay(status)}
                  </span>
                  {order.created_at && (
                    <span className="order-card__date">{formatOrderDate(order.created_at)}</span>
                  )}
                  <div className="order-card__actions">
                    {showTrack(status) && (
                      <button
                        type="button"
                        className="order-card__track-link"
                        onClick={() => {
                          ordersDeepestStageRef.current = 'tracking_modal';
                          track('orders_delivery_modal_open', {
                            orders_session_id: ordersSessionIdRef.current,
                            order_id: order.id,
                          });
                          setTrackingOrder(order);
                        }}
                      >
                        Трек доставки
                      </button>
                    )}
                    {canCancel(status) && (
                      <button
                        type="button"
                        className="order-card__cancel-link"
                        onClick={() => handleCancel(order.id)}
                        disabled={actionLoading === order.id}
                      >
                        Отменить
                      </button>
                    )}
                    {showTrash(status) && (
                      <button
                        type="button"
                        className="order-card__trash"
                        onClick={() => handleHide(order.id)}
                        disabled={actionLoading === order.id}
                        aria-label="Скрыть заказ"
                      >
                        {SVG_TRASH}
                      </button>
                    )}
                  </div>
                </div>
                <div className="order-card__composition">
                  <div className="order-card__composition-items">
                    {items.map((row, idx) => {
                      const name = row.name || 'Товар';
                      const size = (row.size || '').trim() || '—';
                      const stockLabel = getStockLabel(row.stock_type);
                      const pricePerUnit = row.price != null ? Number(row.price) : 0;
                      const qty = row.quantity || 1;
                      const itemId = row.item_id;
                      const photoPath = row.photo ? `/${row.photo}` : null;
                      const titleText = `${name} | ${size} | ${stockLabel}`;
                      const rowInner = (
                        <>
                          <div className="order-card__composition-photo">
                            {photoPath ? (
                              <img src={photoPath} alt="" className="order-card__composition-photo-img" />
                            ) : (
                              <div className="order-card__composition-photo-placeholder" />
                            )}
                          </div>
                          <div className="order-card__composition-title-wrap">
                            <span className="order-card__composition-title-text" title={titleText}>
                              {titleText}
                            </span>
                          </div>
                          <div className="order-card__composition-price-wrap">
                            <span className="order-card__composition-price-text">
                              {qty} * {formatRublesForUser(pricePerUnit)}
                            </span>
                          </div>
                        </>
                      );
                      if (itemId == null) {
                        return (
                          <div
                            key={idx}
                            className="order-card__composition-row order-card__composition-row--static"
                          >
                            {rowInner}
                          </div>
                        );
                      }
                      return (
                        <button
                          key={idx}
                          type="button"
                          className="order-card__composition-row order-card__composition-row--clickable"
                          onClick={() => {
                            track('orders_open_product', {
                              orders_session_id: ordersSessionIdRef.current,
                              order_id: order.id,
                              item_id: itemId,
                            });
                            clearStartappItemRoot();
                            navigate(`/main/catalog/${itemId}`, { state: { fromOrders: true } });
                          }}
                        >
                          {rowInner}
                        </button>
                      );
                    })}
                  </div>
                  <div className="order-card__composition-total">
                    <span className="order-card__composition-total-label">Итого:</span>
                    <span className="order-card__composition-total-value">{formatRublesForUser(total)}</span>
                  </div>
                  {deliveryCost > 0 && (
                    <div className="order-card__composition-total">
                      <span className="order-card__composition-total-label">Доставка:</span>
                      <span className="order-card__composition-total-value">{formatRublesForUser(deliveryCost)}</span>
                    </div>
                  )}
                  {showRemainder && (
                    <>
                      <div className="order-card__composition-total">
                        <span className="order-card__composition-total-label">Остаток:</span>
                        <span className="order-card__composition-total-value">{formatRublesForUser(remainder)}</span>
                      </div>
                      <div className="order-card__composition-total">
                        <span className="order-card__composition-total-label">Внесено:</span>
                        <span className="order-card__composition-total-value">{formatRublesForUser(paid)}</span>
                      </div>
                    </>
                  )}
                  {!showRemainder && paid > 0 && (
                    <div className="order-card__composition-total">
                      <span className="order-card__composition-total-label">Внесено:</span>
                      <span className="order-card__composition-total-value">{formatRublesForUser(paid)}</span>
                    </div>
                  )}
                </div>
                {showRemainder && (
                  <Button
                    type="button"
                    size="small"
                    variant="primary"
                    loading={actionLoading === order.id}
                    disabled={actionLoading === order.id}
                    onClick={() => handlePayRemainder(order)}
                    className="order-card__pay-btn"
                  >
                    Внести остаток
                  </Button>
                )}
                {!showRemainder && showLeaveReview(order) && (
                  <Button
                    type="button"
                    size="small"
                    variant="primary"
                    onClick={() => {
                      ordersDeepestStageRef.current = 'leave_review';
                      track('orders_leave_review_click', {
                        orders_session_id: ordersSessionIdRef.current,
                        order_id: order.id,
                      });
                      navigate(`/main/profile/orders/${order.id}/review`);
                    }}
                    className="order-card__pay-btn"
                  >
                    Оставить отзыв
                  </Button>
                )}
              </article>
            );
          })}
        </div>
      )}
      {trackingOrder && (
        <DeliveryTrackingModal
          order={trackingOrder}
          onClose={() => setTrackingOrder(null)}
        />
      )}
    </div>
  );
}
