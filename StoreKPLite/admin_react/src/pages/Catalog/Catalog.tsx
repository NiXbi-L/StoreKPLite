import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { openAdminPath } from '../../utils/adminNavigation';
import { BulkEditPanel } from './BulkEditPanel';
import './Catalog.css';

const PAGE_SIZE = 50;

interface Item {
  id: number;
  name: string;
  description: string | null;
  price: number;
  service_fee_percent: number;
  estimated_weight_kg: number | null;
  item_type: string;
  gender: string;
  size: string | null;
  link: string | null;
  size_chart_id?: number | null;
  price_rub?: number | null;
  service_fee_amount?: number | null;
  photos: Array<{
    id: number;
    file_path: string;
    telegram_file_id: string | null;
    vk_attachment: string | null;
  }>;
  feed_like_count?: number;
  feed_dislike_count?: number;
}

interface SizeChartOption {
  id: number;
  name: string;
}

interface ItemType {
  id: number;
  name: string;
}

interface StatsByType {
  item_type_id: number;
  item_type: string;
  count: number;
  actual_count: number;
  avg_price_rub: number;
}

const GENDERS = [
  { value: 'М', label: 'Мужской' },
  { value: 'Ж', label: 'Женский' },
  { value: 'унисекс', label: 'Унисекс' }
];

const Catalog: React.FC = () => {
  const [items, setItems] = useState<Item[]>([]);
  const [itemTypes, setItemTypes] = useState<ItemType[]>([]);
  const [sizeCharts, setSizeCharts] = useState<SizeChartOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({
    item_type: '',
    gender: '',
    search: ''
  });
  const [searchInput, setSearchInput] = useState(''); // ввод без задержки, в filters.search попадает с debounce
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [statsByType, setStatsByType] = useState<StatsByType[]>([]);
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  // Debounce поиска: запрос уходит только после паузы в вводе (400 ms)
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters(prev => (prev.search === searchInput ? prev : { ...prev, search: searchInput }));
    }, 400);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    fetchItemTypes();
    fetchPage(0, false);
  }, [filters]);

  const fetchSizeCharts = async () => {
    try {
      const res = await apiClient.get('/products/admin/size-charts');
      setSizeCharts(res.data || []);
    } catch {
      setSizeCharts([]);
    }
  };
  useEffect(() => {
    fetchSizeCharts();
  }, []);

  const fetchItemTypes = async () => {
    try {
      const response = await apiClient.get('/products/admin/item-types');
      setItemTypes(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки типов товаров:', err);
    }
  };

  const fetchPage = useCallback(async (skip: number, append: boolean) => {
    try {
      if (!append) setLoading(true);
      else setLoadingMore(true);
      const params = new URLSearchParams();
      params.set('skip', String(skip));
      params.set('limit', String(PAGE_SIZE));
      if (filters.item_type) params.append('item_type', filters.item_type);
      if (filters.gender) params.append('gender', filters.gender);
      if (filters.search) params.append('search', filters.search);

      const response = await apiClient.get(`/products/admin/items?${params.toString()}`);
      const data = response.data as Item[];
      if (append) {
        setItems((prev) => [...prev, ...data]);
      } else {
        setItems(data);
      }
      setHasMore(data.length === PAGE_SIZE);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки товаров');
      console.error('Ошибка загрузки товаров:', err);
      if (!append) setItems([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [filters.item_type, filters.gender, filters.search]);

  const fetchStatsByType = useCallback(async () => {
    try {
      const res = await apiClient.get('/products/admin/items/stats-by-type');
      setStatsByType(res.data || []);
    } catch {
      setStatsByType([]);
    }
  }, []);

  useEffect(() => {
    fetchItemTypes();
    fetchPage(0, false);
  }, [fetchPage]);

  useEffect(() => {
    fetchStatsByType();
  }, [fetchStatsByType]);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore || loading) return;
    fetchPage(items.length, true);
  }, [hasMore, loadingMore, loading, items.length, fetchPage]);

  useEffect(() => {
    if (!hasMore || loadingMore || loading) return;
    const el = loadMoreSentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: '200px', threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, loadMore]);

  const handleFilterChange = (field: string, value: string) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const handleResetFilters = useCallback(() => {
    setSearchInput('');
    setFilters({ item_type: '', gender: '', search: '' });
  }, []);

  const handleDelete = async (itemId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этот товар?')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/items/${itemId}`);
      setItems(items.filter(item => item.id !== itemId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления товара');
      console.error('Ошибка удаления:', err);
    }
  };

  const handleItemClick = (itemId: number) => {
    openAdminPath(`/catalog/${itemId}`);
  };

  const toggleItemSelection = (itemId: number) => {
    setSelectedItemIds((prev) =>
      prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId]
    );
  };

  const selectAllItems = () => {
    setSelectedItemIds(items.map((i) => i.id));
  };

  const clearSelection = () => {
    setSelectedItemIds([]);
  };

  if (loading) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  return (
    <div className="catalog-page">
      <div className="catalog-header">
        <h1>Каталог товаров</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button
            onClick={async () => {
              if (window.confirm('Обновить file_id и attachment для всех фотографий каталога? Это может занять некоторое время.')) {
                try {
                  setError('');
                  const response = await apiClient.post('/products/admin/items/photos/update-ids');
                  const result = response.data;
                  window.alert(
                    `Обновление завершено!\n` +
                    `Обновлено фотографий: ${result.updated_count}\n` +
                    `Telegram file_id: ${result.telegram_updated}\n` +
                    `VK attachment: ${result.vk_updated}`
                  );
                  // Обновляем список товаров
                  fetchPage(0, false);
                } catch (err: any) {
                  setError(err.response?.data?.detail || 'Ошибка обновления фотографий');
                }
              }
            }}
            className="btn-secondary"
          >
            🔄 Обновить фото каталога
          </button>
          <button onClick={() => navigate('/catalog/groups')} className="btn-secondary">
            📦 Группы товаров
          </button>
          <button onClick={() => navigate('/catalog/types')} className="btn-secondary">
            🏷️ Типы товаров
          </button>
          <button onClick={() => navigate('/catalog/bulk-create')} className="btn-secondary">
            📦 Массовое добавление
          </button>
          <button onClick={() => navigate('/catalog/new')} className="btn-primary">
            Добавить товар
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="catalog-filters">
        <div className="filter-group">
          <label>Тип товара:</label>
          <select
            value={filters.item_type}
            onChange={(e) => handleFilterChange('item_type', e.target.value)}
          >
            <option value="">Все типы</option>
            {itemTypes.map(type => (
              <option key={type.id} value={type.name}>{type.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Пол:</label>
          <select
            value={filters.gender}
            onChange={(e) => handleFilterChange('gender', e.target.value)}
          >
            <option value="">Все</option>
            {GENDERS.map(g => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Поиск по названию:</label>
          <input
            type="text"
            placeholder="Введите название..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <button onClick={handleResetFilters} className="btn-secondary">
          Сбросить
        </button>
      </div>

      {statsByType.length > 0 && (
        <div className="catalog-stats-by-type">
          <h3>Средняя цена по типам</h3>
          <p className="catalog-stats-note">Расчётная цена для клиента (фикс не учитывается)</p>
          <table className="catalog-stats-table">
            <thead>
              <tr>
                <th>Тип</th>
                <th>Кол-во</th>
                <th>Факт. кол-во</th>
                <th>Ср. цена ₽</th>
              </tr>
            </thead>
            <tbody>
              {statsByType.map((row) => (
                <tr key={row.item_type_id}>
                  <td>{row.item_type}</td>
                  <td>{row.count}</td>
                  <td title="Без дублей: в группе каждый тип считается один раз">{row.actual_count}</td>
                  <td>{Number(row.avg_price_rub).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {items.length > 0 && (
        <BulkEditPanel
          selectedIds={selectedItemIds}
          onSuccess={() => fetchPage(0, false)}
          onClearSelection={clearSelection}
          onSelectAll={selectAllItems}
          totalCount={items.length}
          itemTypes={itemTypes}
          sizeCharts={sizeCharts}
          fetchSizeCharts={fetchSizeCharts}
          setError={setError}
          selectionLabel="Массовое изменение:"
        />
      )}

      {/* Таблица для десктопа */}
      <div className="catalog-table-container">
        {items.length === 0 ? (
          <div className="no-data">Товары не найдены</div>
        ) : (
          <table className="catalog-table">
            <thead>
              <tr>
                <th style={{ width: 40 }}>
                  <input
                    type="checkbox"
                    checked={items.length > 0 && selectedItemIds.length === items.length}
                    onChange={(e) => (e.target.checked ? selectAllItems() : clearSelection())}
                  />
                </th>
                <th>ID</th>
                <th>Название</th>
                <th>Тип</th>
                <th>Пол</th>
                <th>Лента 👍/👎</th>
                <th>Цена (¥)</th>
                <th>Превью</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedItemIds.includes(item.id)}
                      onChange={() => toggleItemSelection(item.id)}
                    />
                  </td>
                  <td>{item.id}</td>
                  <td><strong>{item.name}</strong></td>
                  <td>{item.item_type}</td>
                  <td>{item.gender}</td>
                  <td title="Лайки и дизлайки в ленте (уникальные пользователи)">
                    {item.feed_like_count ?? 0} / {item.feed_dislike_count ?? 0}
                  </td>
                  <td>
                    <div>{item.price} ¥</div>
                    {item.price_rub != null && (
                      <div className="catalog-price-rub">
                        <div>Итого: {Number(item.price_rub).toFixed(0)} ₽</div>
                        {item.service_fee_amount != null && (
                          <div className="catalog-fee">Наценка: {Number(item.service_fee_amount).toFixed(0)} ₽</div>
                        )}
                      </div>
                    )}
                  </td>
                  <td>
                    {item.photos && item.photos.length > 0 ? (
                      <div className="item-preview">
                        <img
                          src={`/${item.photos[0].file_path}`}
                          alt={item.name}
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                          }}
                        />
                        <small>{item.photos.length} фото</small>
                      </div>
                    ) : (
                      <span className="no-photo">Нет фото</span>
                    )}
                  </td>
                  <td>
                    <button
                      onClick={() => handleItemClick(item.id)}
                      className="btn-view"
                    >
                      Просмотр
                    </button>
                    <button
                      onClick={() => navigate(`/catalog/${item.id}/edit`)}
                      className="btn-edit"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDelete(item.id)}
                      className="btn-delete"
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Карточки для мобильных */}
      <div className="catalog-cards-container">
        {items.length === 0 ? (
          <div className="no-data">Товары не найдены</div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="catalog-card">
              <div className="catalog-card-header">
                <label className="catalog-card-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedItemIds.includes(item.id)}
                    onChange={() => toggleItemSelection(item.id)}
                  />
                </label>
                <h3>{item.name}</h3>
                <div className="catalog-card-id">#{item.id}</div>
              </div>
              <div className="catalog-card-body">
                {item.photos && item.photos.length > 0 && (
                  <div className="catalog-card-photo">
                    <img
                      src={`/${item.photos[0].file_path}`}
                      alt={item.name}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                    <small>{item.photos.length} фото</small>
                  </div>
                )}
                <div className="catalog-card-field">
                  <label>Тип:</label>
                  <div>{item.item_type}</div>
                </div>
                <div className="catalog-card-field">
                  <label>Пол:</label>
                  <div>{item.gender}</div>
                </div>
                <div className="catalog-card-field">
                  <label>Лента (лайк / дизлайк):</label>
                  <div>
                    {item.feed_like_count ?? 0} / {item.feed_dislike_count ?? 0}
                  </div>
                </div>
                <div className="catalog-card-field">
                  <label>Цена:</label>
                  <div><strong>{item.price} ¥</strong></div>
                </div>
                <div className="catalog-card-actions">
                  <button
                    onClick={() => handleItemClick(item.id)}
                    className="btn-view"
                  >
                    Просмотр
                  </button>
                  <button
                    onClick={() => navigate(`/catalog/${item.id}/edit`)}
                    className="btn-edit"
                  >
                    Редактировать
                  </button>
                  <button
                    onClick={() => handleDelete(item.id)}
                    className="btn-delete"
                  >
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {hasMore && <div ref={loadMoreSentinelRef} className="catalog-load-more-sentinel" aria-hidden />}
      {loadingMore && <div className="catalog-loading-more">Загрузка ещё…</div>}
    </div>
  );
};

export default Catalog;
