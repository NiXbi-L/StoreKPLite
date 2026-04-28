import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCartItems, updateCartItemSize } from '../../api/products';
import Button from '../../components/Button';
import CartItemCard from '../../components/CartItemCard';
import { formatRublesForUser } from '../../utils/formatRubles';
import { track } from '../../utils/productAnalytics';
import './CartPage.css';

export default function CartPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [toast, setToast] = useState(null);
  const cartViewTrackedRef = useRef(false);

  const loadCart = useCallback(async (opts = {}) => {
    const silent = opts.silent === true;
    try {
      if (!silent) {
        setLoading(true);
        setError(null);
      }
      const data = await getCartItems();
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      if (!silent) {
        setError(e.message || 'Не удалось загрузить корзину');
        setItems([]);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCart();
  }, [loadCart]);

  useEffect(() => {
    if (loading || cartViewTrackedRef.current) return;
    cartViewTrackedRef.current = true;
    track('cart_view', {
      lines: items.length,
      mode: 'single',
    });
  }, [loading, items.length]);

  useEffect(() => {
    const onInvalidate = () => loadCart({ silent: true });
    window.addEventListener('miniapp-invalidate-cart', onInvalidate);
    return () => window.removeEventListener('miniapp-invalidate-cart', onInvalidate);
  }, [loadCart]);

  const handleSelect = (cartItemId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(cartItemId)) next.delete(cartItemId);
      else next.add(cartItemId);
      return next;
    });
  };

  const handleDeleted = (deletedId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(deletedId);
      return next;
    });
    loadCart();
  };

  const handleQuantityChange = (cartItem, newQuantity, reason) => {
    if (reason === 'limit') {
      setToast('Нельзя добавить больше 50 единиц товара');
      setTimeout(() => setToast(null), 3000);
      return;
    }

    setItems((prev) => {
      if (newQuantity <= 0) {
        return prev.filter((it) => it.id !== cartItem.id);
      }
      return prev.map((it) =>
        it.id === cartItem.id ? { ...it, quantity: newQuantity } : it
      );
    });
  };

  const handleSizeChange = async (cartItem, newSize) => {
    const normalized = (newSize || '').trim();
    if (!normalized || normalized === (cartItem.size || '')) return;
    // Оптимистично обновляем локальное состояние: либо меняем размер, либо объединяем с существующей позицией
    setItems((prev) => {
      const itemsCopy = [...prev];
      const idx = itemsCopy.findIndex((it) => it.id === cartItem.id);
      if (idx === -1) return prev;
      const current = itemsCopy[idx];

      const same = itemsCopy.find(
        (it) =>
          it.id !== current.id &&
          it.item.id === current.item.id &&
          (it.size || '') === normalized &&
          it.stock_type === current.stock_type,
      );

      if (same) {
        same.quantity += current.quantity;
        itemsCopy.splice(idx, 1);
      } else {
        itemsCopy[idx] = { ...current, size: normalized };
      }
      return itemsCopy;
    });

    try {
      await updateCartItemSize(cartItem.id, normalized);
    } catch (e) {
      setError(e.message || 'Не удалось изменить размер');
      // В случае ошибки можно перезагрузить корзину, чтобы вернуть корректное состояние
      loadCart();
    }
  };

  const filteredItems = items;

  const totalPrice = useMemo(() => {
    if (!filteredItems.length || !selectedIds.size) return 0;
    return filteredItems.reduce((sum, cartItem) => {
      if (!selectedIds.has(cartItem.id)) return sum;
      const item = cartItem.item || {};
      const pricePerUnit = Number(cartItem.price_rub ?? item.fixed_price_rub ?? item.price_rub ?? 0);
      if (!Number.isFinite(pricePerUnit)) return sum;
      return sum + pricePerUnit * (cartItem.quantity || 1);
    }, 0);
  }, [filteredItems, selectedIds]);

  return (
    <div className="cart-page">
      <div className="cart-page__inner page-container">
        {toast && (
          <div className="cart-page__toast">
            <div className="cart-page__toast-inner">
              {toast}
            </div>
          </div>
        )}
        {loading && (
          <p className="cart-page__loading">Загрузка…</p>
        )}
        {error && (
          <p className="cart-page__error" role="alert">{error}</p>
        )}
        {!loading && !error && filteredItems.length === 0 && (
          <p className="cart-page__empty">В корзине пока ничего нет</p>
        )}
        {!loading && !error && filteredItems.length > 0 && (
          <ul className="cart-page__list">
            {filteredItems.map((cartItem) => (
              <li key={cartItem.id} className="cart-page__list-item">
                <CartItemCard
                  cartItem={cartItem}
                  selected={selectedIds.has(cartItem.id)}
                  onSelect={handleSelect}
                  onQuantityChange={handleQuantityChange}
                  onDeleted={handleDeleted}
                  onSizeChange={handleSizeChange}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
      {totalPrice > 0 && selectedIds.size > 0 && (
        <div className="cart-page__checkout">
          <div className="cart-page__checkout-inner">
            <div className="cart-page__checkout-bg" />
            <div className="cart-page__checkout-content">
              <div className="cart-page__checkout-price-wrap">
                <span className="cart-page__checkout-price">
                  {formatRublesForUser(totalPrice)}
                </span>
              </div>
              <div className="cart-page__checkout-btn-wrap">
                <Button
                  size="small"
                  variant="primary"
                  className="cart-page__checkout-btn"
                  onClick={() => {
                    const ids = Array.from(selectedIds);
                    track('cart_checkout_click', {
                      selected_count: ids.length,
                      mode: 'single',
                    });
                    navigate('/main/checkout', {
                      state: { selectedCartItemIds: ids },
                    });
                  }}
                >
                  Перейти к оформлению
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
