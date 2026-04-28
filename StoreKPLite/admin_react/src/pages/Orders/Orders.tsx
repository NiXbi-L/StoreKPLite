import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Orders.css';

interface OrderItem {
  name: string;
  quantity: number;
  price: number;
}

interface Order {
  id: number;
  status: string;
  created_at: string;
  paid_amount: number;
  order_data: { items?: OrderItem[] };
  phone_number: string | null;
  tracking_number: string | null;
}

interface AdminOrderListPayload {
  items: Order[];
}

const STATUSES = [
  { value: '', label: 'Все статусы' },
  { value: 'Ожидает', label: 'Ожидает' },
  { value: 'Выкуп', label: 'Выкуп' },
  { value: 'в работе', label: 'В работе' },
  { value: 'Собран', label: 'Собран' },
  { value: 'отменен', label: 'Отменен' },
  { value: 'завершен', label: 'Завершен' },
];

const Orders: React.FC = () => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [refundModalOrderId, setRefundModalOrderId] = useState<number | null>(null);
  const [refundAmount, setRefundAmount] = useState('');
  const [refundReason, setRefundReason] = useState('');
  const [refundSubmitting, setRefundSubmitting] = useState(false);

  const fetchOrders = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.set('skip', '0');
      params.set('limit', '200');
      if (statusFilter) params.append('status_filter', statusFilter);
      if (searchQuery) params.append('search', searchQuery);
      const response = await apiClient.get<AdminOrderListPayload>(`/products/admin/orders?${params.toString()}`);
      setOrders(response.data.items || []);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки заказов');
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchQuery]);

  useEffect(() => {
    void fetchOrders();
  }, [fetchOrders]);

  const handleStatusChange = async (orderId: number, newStatus: string, currentStatus: string) => {
    if (currentStatus === 'отменен' || currentStatus === 'завершен') return;
    try {
      await apiClient.post(`/products/admin/orders/${orderId}/status`, {
        new_status: newStatus,
        cancel_reason: null,
      });
      await fetchOrders();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления статуса');
    }
  };

  const handlePaidAmountChange = async (orderId: number, newAmount: number, currentAmount: number) => {
    if (Math.abs(newAmount - currentAmount) < 0.01) return;
    try {
      await apiClient.post(`/products/admin/orders/${orderId}/paid-amount`, { paid_amount: newAmount });
      await fetchOrders();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления внесенных средств');
      await fetchOrders();
    }
  };

  const handleDeliveryDataChange = async (orderId: number, field: 'phone_number' | 'tracking_number', value: string) => {
    try {
      await apiClient.patch(`/products/admin/orders/${orderId}/delivery-data`, { [field]: value.trim() || null });
      await fetchOrders();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления данных доставки');
    }
  };

  const handleRefundSubmit = async () => {
    if (refundModalOrderId == null) return;
    setRefundSubmitting(true);
    try {
      const payload: { amount?: number; reason?: string } = {};
      const amountNum = parseFloat(refundAmount.replace(',', '.'));
      if (!isNaN(amountNum) && amountNum > 0) payload.amount = amountNum;
      if (refundReason.trim()) payload.reason = refundReason.trim();
      await apiClient.post(`/products/admin/orders/${refundModalOrderId}/refund`, payload);
      setRefundModalOrderId(null);
      setRefundAmount('');
      setRefundReason('');
      await fetchOrders();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка возврата');
    } finally {
      setRefundSubmitting(false);
    }
  };

  return (
    <div className="orders-page">
      <div className="orders-header">
        <h1>Заказы</h1>
        <button className="btn-primary" onClick={() => navigate('/orders/manual')}>
          + Создать заказ вручную
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="filters-section">
        <div className="filter-group">
          <label htmlFor="status_filter">Статус:</label>
          <select id="status_filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            {STATUSES.map(status => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="search_input">Номер заказа:</label>
          <input
            type="number"
            id="search_input"
            placeholder="Введите номер..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') void fetchOrders();
            }}
          />
        </div>

        <button
          onClick={() => {
            setStatusFilter('');
            setSearchQuery('');
          }}
          className="btn-reset"
        >
          Сбросить
        </button>
      </div>

      {loading ? (
        <div className="loading">Загрузка заказов...</div>
      ) : orders.length === 0 ? (
        <div className="no-orders">Заказов пока нет.</div>
      ) : (
        <div className="orders-table-container">
          <table className="orders-table">
            <thead>
              <tr>
                <th>Номер</th>
                <th>Состав</th>
                <th>Статус</th>
                <th>Трекинг и телефон</th>
                <th>Внесено</th>
                <th>Дата</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => (
                <tr key={order.id}>
                  <td>
                    <strong>#{order.id}</strong>
                  </td>
                  <td>
                    {(order.order_data?.items || []).length > 0 ? (
                      (order.order_data.items || []).map((item, idx) => (
                        <div key={idx}>
                          {item.name} - {item.quantity} шт. x {item.price.toFixed(2)} ₽
                        </div>
                      ))
                    ) : (
                      <span className="no-data">Нет данных</span>
                    )}
                  </td>
                  <td>
                    {order.status === 'отменен' || order.status === 'завершен' ? (
                      <span>{order.status}</span>
                    ) : (
                      <select value={order.status} onChange={e => handleStatusChange(order.id, e.target.value, order.status)}>
                        <option value="Ожидает">Ожидает</option>
                        <option value="Выкуп">Выкуп</option>
                        <option value="в работе">В работе</option>
                        <option value="Собран">Собран</option>
                        <option value="отменен">Отменен</option>
                        <option value="завершен">Завершен</option>
                      </select>
                    )}
                  </td>
                  <td>
                    <div style={{ marginBottom: 8 }}>
                      <strong>Трек:</strong>
                      <input
                        type="text"
                        value={order.tracking_number || ''}
                        onChange={e => handleDeliveryDataChange(order.id, 'tracking_number', e.target.value)}
                        onBlur={e => handleDeliveryDataChange(order.id, 'tracking_number', e.target.value)}
                        placeholder="Трек-номер"
                        style={{ width: '100%', marginTop: 4 }}
                      />
                    </div>
                    <div>
                      <strong>Телефон:</strong>
                      <input
                        type="text"
                        value={order.phone_number || ''}
                        onChange={e => handleDeliveryDataChange(order.id, 'phone_number', e.target.value)}
                        onBlur={e => handleDeliveryDataChange(order.id, 'phone_number', e.target.value)}
                        placeholder="+7XXXXXXXXXX"
                        style={{ width: '100%', marginTop: 4 }}
                      />
                    </div>
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      defaultValue={order.paid_amount.toFixed(2)}
                      onBlur={e => {
                        const newValue = parseFloat(e.target.value) || 0;
                        void handlePaidAmountChange(order.id, newValue, order.paid_amount);
                      }}
                    />
                    <span style={{ marginLeft: 6 }}>₽</span>
                    {order.paid_amount > 0 && (
                      <div>
                        <button
                          type="button"
                          className="btn-refund-inline"
                          onClick={() => {
                            setRefundModalOrderId(order.id);
                            setRefundAmount('');
                            setRefundReason('');
                          }}
                        >
                          ↩ Возврат
                        </button>
                      </div>
                    )}
                  </td>
                  <td>{new Date(order.created_at).toLocaleString('ru-RU')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {refundModalOrderId != null && (
        <div className="modal-overlay" onClick={() => !refundSubmitting && setRefundModalOrderId(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
            <h3>Возврат по заказу #{refundModalOrderId}</h3>
            <div className="form-group">
              <label>Сумма возврата (₽), пусто = полный возврат</label>
              <input
                type="text"
                inputMode="decimal"
                value={refundAmount}
                onChange={e => setRefundAmount(e.target.value)}
                placeholder="Например: 1500.50"
              />
            </div>
            <div className="form-group">
              <label>Причина</label>
              <input
                type="text"
                value={refundReason}
                onChange={e => setRefundReason(e.target.value)}
                placeholder="Причина возврата"
              />
            </div>
            <div className="form-actions" style={{ marginTop: 16 }}>
              <button type="button" className="btn-secondary" onClick={() => setRefundModalOrderId(null)} disabled={refundSubmitting}>
                Отмена
              </button>
              <button type="button" className="btn-primary" onClick={handleRefundSubmit} disabled={refundSubmitting}>
                {refundSubmitting ? 'Выполняется...' : 'Выполнить возврат'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Orders;
