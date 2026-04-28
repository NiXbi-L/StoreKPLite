import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { openAdminPath } from '../../utils/adminNavigation';
import { getTelegramCaptionLength, TELEGRAM_CAPTION_MAX_LENGTH } from '../../utils/telegramUtils';
import { BulkEditPanel } from './BulkEditPanel';
import './Catalog.css';

interface ItemGroupDetail {
  id: number;
  name: string;
  created_at: string;
  items: Array<{
    id: number;
    name: string;
    price: number;
    item_type: string;
    gender: string;
    size: string | null;
    photos_count: number;
    is_legit?: boolean | null;
  }>;
}

interface Item {
  id: number;
  name: string;
  price: number;
  item_type: string;
  gender: string;
}

interface SizeChartOption {
  id: number;
  name: string;
}

interface ItemTypeOption {
  id: number;
  name: string;
}

const ItemGroupDetail: React.FC = () => {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const [group, setGroup] = useState<ItemGroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAddItemsModal, setShowAddItemsModal] = useState(false);
  const [availableItems, setAvailableItems] = useState<Item[]>([]);
  const [filteredItems, setFilteredItems] = useState<Item[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [editingGroupName, setEditingGroupName] = useState('');
  const [showEditModal, setShowEditModal] = useState(false);
  const [showPriceModal, setShowPriceModal] = useState(false);
  const [showServiceFeeModal, setShowServiceFeeModal] = useState(false);
  const [newPrice, setNewPrice] = useState('');
  const [newServiceFee, setNewServiceFee] = useState('');
  const [showPostModal, setShowPostModal] = useState(false);
  const [postData, setPostData] = useState<{
    group: { id: number; name: string };
    items: Array<{ id: number; name: string; size: string[] | null; current_price_rub: number | null; item_type: string | null }>;
    photos: Array<{ id: number; file_path: string; telegram_file_id: string; item_id: number }>;
  } | null>(null);
  const [postText, setPostText] = useState('');
  const [postPhotoIds, setPostPhotoIds] = useState<number[]>([]);
  const [additionalPostFiles, setAdditionalPostFiles] = useState<File[]>([]);
  const [postLoading, setPostLoading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [groupItemSelection, setGroupItemSelection] = useState<number[]>([]);
  const [sizeCharts, setSizeCharts] = useState<SizeChartOption[]>([]);
  const [itemTypes, setItemTypes] = useState<ItemTypeOption[]>([]);

  const BOT_USERNAME = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || '';

  const toggleGroupItemSelection = (itemId: number) => {
    setGroupItemSelection((prev) =>
      prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId]
    );
  };

  const selectAllGroupItems = () => {
    if (!group) return;
    setGroupItemSelection(group.items.map((i) => i.id));
  };

  const clearGroupItemSelection = () => {
    setGroupItemSelection([]);
  };

  const fetchSizeCharts = async () => {
    try {
      const response = await apiClient.get('/products/admin/size-charts');
      setSizeCharts(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки таблиц размеров:', err);
    }
  };

  const fetchItemTypes = async () => {
    try {
      const response = await apiClient.get('/products/admin/item-types');
      setItemTypes(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки типов товаров:', err);
    }
  };

  useEffect(() => {
    if (groupId) {
      fetchGroupDetail(parseInt(groupId));
    }
  }, [groupId]);

  useEffect(() => {
    if (group && group.items.length > 0) {
      fetchSizeCharts();
      fetchItemTypes();
    }
  }, [group?.id]);

  // Фильтрация товаров по поисковому запросу
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredItems(availableItems);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = availableItems.filter(item =>
        item.name.toLowerCase().includes(query) ||
        item.item_type.toLowerCase().includes(query) ||
        item.gender.toLowerCase().includes(query) ||
        String(item.id).includes(query)
      );
      setFilteredItems(filtered);
    }
  }, [searchQuery, availableItems]);

  const fetchGroupDetail = async (id: number) => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/products/admin/item-groups/${id}`);
      setGroup(response.data);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки группы');
      console.error('Ошибка загрузки группы:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableItems = async () => {
    try {
      const response = await apiClient.get('/products/admin/items');
      // Фильтруем только товары без группы (group_id должен быть null или undefined)
      const itemsWithoutGroup = response.data.filter((item: any) => 
        item.group_id === null || item.group_id === undefined
      );
      setAvailableItems(itemsWithoutGroup);
      setFilteredItems(itemsWithoutGroup);
      setSearchQuery('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки товаров');
      console.error('Ошибка загрузки товаров:', err);
    }
  };

  const handleUpdateGroup = async () => {
    if (!groupId || !editingGroupName.trim()) {
      setError('Название группы не может быть пустым');
      return;
    }

    try {
      await apiClient.put(`/products/admin/item-groups/${groupId}`, { name: editingGroupName });
      setShowEditModal(false);
      setEditingGroupName('');
      await fetchGroupDetail(parseInt(groupId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления группы');
      console.error('Ошибка обновления группы:', err);
    }
  };

  const handleDeleteGroup = async () => {
    if (!groupId || !window.confirm('Вы уверены, что хотите удалить эту группу? Товары останутся, но будут без группы.')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/item-groups/${groupId}`);
      navigate('/catalog/groups');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления группы');
      console.error('Ошибка удаления группы:', err);
    }
  };

  const handleAddItemsToGroup = async () => {
    if (!groupId || selectedItemIds.length === 0) {
      setError('Выберите хотя бы один товар');
      return;
    }

    try {
      await apiClient.post(`/products/admin/item-groups/${groupId}/items`, {
        item_ids: selectedItemIds
      });
      setShowAddItemsModal(false);
      setSelectedItemIds([]);
      await fetchGroupDetail(parseInt(groupId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка добавления товаров');
      console.error('Ошибка добавления товаров:', err);
    }
  };

  const handleRemoveItemFromGroup = async (itemId: number) => {
    if (!groupId || !window.confirm('Удалить этот товар из группы?')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/item-groups/${groupId}/items/${itemId}`);
      await fetchGroupDetail(parseInt(groupId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления товара из группы');
      console.error('Ошибка удаления товара из группы:', err);
    }
  };

  const openAddItemsModal = async () => {
    setShowAddItemsModal(true);
    setSelectedItemIds([]);
    setSearchQuery('');
    await fetchAvailableItems();
  };

  const openEditModal = () => {
    if (group) {
      setEditingGroupName(group.name);
      setShowEditModal(true);
    }
  };

  const openPriceModal = () => {
    if (group && group.items.length > 0) {
      // Устанавливаем текущую цену первого товара как начальное значение
      setNewPrice(String(group.items[0].price));
      setShowPriceModal(true);
    }
  };

  const openServiceFeeModal = () => {
    if (group && group.items.length > 0) {
      // Устанавливаем начальное значение 0
      setNewServiceFee('0');
      setShowServiceFeeModal(true);
    }
  };

  const generateGroupPostTemplate = (data: NonNullable<typeof postData>) => {
    const allSizes = new Set<string>();
    data.items.forEach((it) => {
      if (it.size && Array.isArray(it.size)) it.size.forEach((s) => allSizes.add(s));
    });
    const sizeText = allSizes.size > 0 ? `(${Array.from(allSizes).join(', ')})` : '(Не указан)';
    const priceLines = data.items.map((it) => {
      const price = it.current_price_rub != null
        ? (typeof it.current_price_rub === 'number' ? it.current_price_rub.toFixed(2) : Number(it.current_price_rub).toFixed(2))
        : '—';
      const itemUrl = `https://t.me/${BOT_USERNAME}?startapp=item_${it.id}`;
      return `<a href="${itemUrl}">${it.name}</a>: ${price} ₽`;
    }).join('\n');
    const uniqueTypes = Array.from(
      new Set(data.items.map((it) => it.item_type).filter((t): t is string => Boolean(t)))
    );
    const typeHashtags = uniqueTypes.map((t) => `#${t.replace(/\s+/g, '_')}`).join(' ');

    return `${data.group.name} 🖤

Размеры: ${sizeText}

Доставка по всей России 🌎
Личная встреча г. Уссурийск

💰ЦЕНЫ💰
${priceLines}
(актуальная цена в боте)

<a href="https://t.me/Timoshka_otzivi">ОТЗЫВЫ</a>

💬 Вопросы? В боте: Поддержка → FAQ${typeHashtags ? `\n\n${typeHashtags}` : ''}`;
  };

  const handleOpenPostModal = async () => {
    if (!groupId) return;
    setPostLoading(true);
    setError('');
    try {
      const response = await apiClient.get(`/products/admin/item-groups/${groupId}/post-data`);
      const data = response.data;
      setPostData(data);
      setPostText(generateGroupPostTemplate(data));
      const photoIds = data.photos.slice(0, 10).map((p: { id: number }) => p.id);
      setPostPhotoIds(photoIds);
      setShowPostModal(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки данных для поста');
    } finally {
      setPostLoading(false);
    }
  };

  const handleClosePostModal = () => {
    setShowPostModal(false);
    setPostData(null);
    setPostText('');
    setPostPhotoIds([]);
    setAdditionalPostFiles([]);
  };

  const togglePostPhoto = (photoId: number) => {
    setPostPhotoIds((prev) => {
      if (prev.includes(photoId)) {
        return prev.filter((id) => id !== photoId);
      }
      if (prev.length >= 10) return prev;
      return [...prev, photoId];
    });
  };

  const movePostPhoto = (fromIndex: number, direction: 'up' | 'down') => {
    setPostPhotoIds((prev) => {
      if (direction === 'up' && fromIndex <= 0) return prev;
      if (direction === 'down' && fromIndex >= prev.length - 1) return prev;
      const toIndex = direction === 'up' ? fromIndex - 1 : fromIndex + 1;
      const arr = [...prev];
      [arr[fromIndex], arr[toIndex]] = [arr[toIndex], arr[fromIndex]];
      return arr;
    });
  };

  const moveAdditionalPhoto = (fromIndex: number, direction: 'up' | 'down') => {
    setAdditionalPostFiles((prev) => {
      if (direction === 'up' && fromIndex <= 0) return prev;
      if (direction === 'down' && fromIndex >= prev.length - 1) return prev;
      const toIndex = direction === 'up' ? fromIndex - 1 : fromIndex + 1;
      const arr = [...prev];
      [arr[fromIndex], arr[toIndex]] = [arr[toIndex], arr[fromIndex]];
      return arr;
    });
  };

  const handlePostToTelegram = async () => {
    const totalPhotos = postPhotoIds.length + additionalPostFiles.length;
    if (!groupId || !postText.trim()) {
      setError('Заполните текст поста');
      return;
    }
    if (totalPhotos === 0) {
      setError('Выберите фото из каталога или загрузите свои');
      return;
    }
    if (totalPhotos > 10) {
      setError('Максимум 10 фото в посте');
      return;
    }
    const captionLen = getTelegramCaptionLength(postText);
    if (captionLen > TELEGRAM_CAPTION_MAX_LENGTH) {
      setError(`Текст поста превышает лимит (${captionLen} > ${TELEGRAM_CAPTION_MAX_LENGTH} символов)`);
      return;
    }
    try {
      setPosting(true);
      setError('');
      const form = new FormData();
      form.append('message_text', postText);
      form.append('photo_ids', JSON.stringify(postPhotoIds));
      additionalPostFiles.forEach((f) => form.append('additional_photos', f));
      await apiClient.post(`/products/admin/item-groups/${groupId}/post-to-telegram`, form);
      alert('Пост успешно отправлен в Telegram канал!');
      handleClosePostModal();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка отправки поста');
    } finally {
      setPosting(false);
    }
  };

  const handleUpdateGroupPrice = async () => {
    if (!groupId || !newPrice || parseFloat(newPrice) <= 0) {
      setError('Введите корректную цену (больше 0)');
      return;
    }

    try {
      await apiClient.put(`/products/admin/item-groups/${groupId}/items/price`, {
        price: parseFloat(newPrice)
      });
      setShowPriceModal(false);
      setNewPrice('');
      await fetchGroupDetail(parseInt(groupId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления цены');
      console.error('Ошибка обновления цены:', err);
    }
  };

  const handleUpdateGroupServiceFee = async () => {
    if (!groupId || newServiceFee === '' || parseFloat(newServiceFee) < 0) {
      setError('Введите корректный сервисный сбор (больше или равно 0)');
      return;
    }

    try {
      await apiClient.put(`/products/admin/item-groups/${groupId}/items/service-fee`, {
        service_fee_percent: parseFloat(newServiceFee)
      });
      setShowServiceFeeModal(false);
      setNewServiceFee('');
      await fetchGroupDetail(parseInt(groupId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления сервисного сбора');
      console.error('Ошибка обновления сервисного сбора:', err);
    }
  };

  if (loading) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  if (error && !group) {
    return (
      <div className="catalog-page">
        <div className="error-message">{error}</div>
        <button onClick={() => navigate('/catalog/groups')} className="btn-secondary">
          Назад к группам
        </button>
      </div>
    );
  }

  if (!group) {
    return null;
  }

  return (
    <div className="catalog-page">
      <div className="item-detail-header">
        <h1>{group.name}</h1>
        <div className="item-detail-actions">
          <button onClick={openEditModal} className="btn-edit">
            Редактировать название
          </button>
          <button onClick={openAddItemsModal} className="btn-primary">
            Добавить товары
          </button>
          <button
            onClick={handleOpenPostModal}
            className="btn-primary"
            disabled={postLoading || group.items.length === 0}
            title={group.items.length === 0 ? 'Сначала добавьте товары в группу' : undefined}
          >
            {postLoading ? 'Загрузка...' : '📢 Сделать пост'}
          </button>
          {group.items.length > 0 && (
            <>
              <button onClick={openPriceModal} className="btn-primary" style={{ backgroundColor: '#28a745' }}>
                Изменить цену для всех товаров
              </button>
              <button onClick={openServiceFeeModal} className="btn-primary" style={{ backgroundColor: '#17a2b8' }}>
                Изменить сервисный сбор для всех товаров
              </button>
            </>
          )}
          <button onClick={handleDeleteGroup} className="btn-delete">
            Удалить группу
          </button>
          <button onClick={() => navigate('/catalog/groups')} className="btn-secondary">
            Назад к группам
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="item-detail-card">
        <h2>Информация о группе</h2>
        <div className="detail-row">
          <label>Название:</label>
          <div>{group.name}</div>
        </div>
        <div className="detail-row">
          <label>Товаров в группе:</label>
          <div><strong>{group.items.length}</strong></div>
        </div>
      </div>

      <div className="item-photos-section">
        <h2>Товары в группе</h2>
        {group.items.length === 0 ? (
          <p>В этой группе пока нет товаров</p>
        ) : (
          <>
            <BulkEditPanel
              selectedIds={groupItemSelection}
              onSuccess={() => fetchGroupDetail(parseInt(groupId!))}
              onClearSelection={clearGroupItemSelection}
              onSelectAll={selectAllGroupItems}
              totalCount={group.items.length}
              itemTypes={itemTypes}
              sizeCharts={sizeCharts}
              fetchSizeCharts={fetchSizeCharts}
              setError={setError}
              selectionLabel="Массовое изменение:"
              className="group-bulk-actions"
            />
            {/* Таблица для десктопа */}
            <div className="catalog-table-container">
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>
                      <input
                        type="checkbox"
                        checked={group.items.length > 0 && groupItemSelection.length === group.items.length}
                        onChange={(e) => (e.target.checked ? selectAllGroupItems() : clearGroupItemSelection())}
                      />
                    </th>
                    <th>ID</th>
                    <th>Название</th>
                    <th>Легит</th>
                    <th>Тип</th>
                    <th>Пол</th>
                    <th>Цена (¥)</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {group.items.map(item => (
                    <tr key={item.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={groupItemSelection.includes(item.id)}
                          onChange={() => toggleGroupItemSelection(item.id)}
                        />
                      </td>
                      <td>{item.id}</td>
                      <td><strong>{item.name}</strong></td>
                      <td>{item.is_legit === true ? 'Оригинал' : item.is_legit === false ? 'Реплика' : '—'}</td>
                      <td>{item.item_type}</td>
                      <td>{item.gender}</td>
                      <td>{item.price} ¥</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => openAdminPath(`/catalog/${item.id}`)}
                          className="btn-view"
                        >
                          Просмотр
                        </button>
                        <button
                          onClick={() => handleRemoveItemFromGroup(item.id)}
                          className="btn-delete"
                        >
                          Удалить из группы
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Карточки для мобильных */}
            <div className="catalog-cards-container group-items-cards">
              {group.items.map(item => (
                <div key={item.id} className="catalog-card">
                  <div className="catalog-card-header">
                    <label className="catalog-card-checkbox">
                      <input
                        type="checkbox"
                        checked={groupItemSelection.includes(item.id)}
                        onChange={() => toggleGroupItemSelection(item.id)}
                      />
                    </label>
                    <h3>{item.name}</h3>
                    <div className="catalog-card-id">#{item.id}</div>
                  </div>
                  <div className="catalog-card-body">
                    <div className="catalog-card-field">
                      <label>Легит:</label>
                      <div>{item.is_legit === true ? 'Оригинал' : item.is_legit === false ? 'Реплика' : '—'}</div>
                    </div>
                    <div className="catalog-card-field">
                      <label>Тип:</label>
                      <div>{item.item_type}</div>
                    </div>
                    <div className="catalog-card-field">
                      <label>Пол:</label>
                      <div>{item.gender}</div>
                    </div>
                    <div className="catalog-card-field">
                      <label>Цена:</label>
                      <div><strong>{item.price} ¥</strong></div>
                    </div>
                    {item.size && (
                      <div className="catalog-card-field">
                        <label>Размеры:</label>
                        <div>{Array.isArray(item.size) ? item.size.join(', ') : item.size}</div>
                      </div>
                    )}
                    <div className="catalog-card-actions">
                      <button
                        type="button"
                        onClick={() => openAdminPath(`/catalog/${item.id}`)}
                        className="btn-view"
                      >
                        Просмотр
                      </button>
                      <button
                        onClick={() => handleRemoveItemFromGroup(item.id)}
                        className="btn-delete"
                      >
                        Удалить из группы
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Модальное окно редактирования группы */}
      {showEditModal && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Редактировать группу</h2>
              <button className="modal-close" onClick={() => setShowEditModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Название группы *</label>
                <input
                  type="text"
                  value={editingGroupName}
                  onChange={(e) => setEditingGroupName(e.target.value)}
                  autoFocus
                />
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={handleUpdateGroup} className="btn-primary">
                Сохранить
              </button>
              <button onClick={() => setShowEditModal(false)} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно добавления товаров */}
      {showAddItemsModal && (
        <div className="modal-overlay" onClick={() => setShowAddItemsModal(false)}>
          <div className="modal-content" style={{ maxWidth: '800px' }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Добавить товары в группу "{group.name}"</h2>
              <button className="modal-close" onClick={() => setShowAddItemsModal(false)}>×</button>
            </div>
            <div className="modal-body" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
              {availableItems.length === 0 ? (
                <div>Нет доступных товаров (все товары уже в группах)</div>
              ) : (
                <div>
                  <p>Выберите товары для добавления в группу:</p>
                  <div className="form-group" style={{ marginTop: '1rem', marginBottom: '1rem' }}>
                    <label>Поиск товаров:</label>
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Поиск по названию, типу, полу или ID..."
                      style={{ width: '100%', padding: '0.5rem' }}
                    />
                    {searchQuery && (
                      <small style={{ display: 'block', marginTop: '0.25rem', color: '#666' }}>
                        Найдено: {filteredItems.length} из {availableItems.length}
                      </small>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '1rem' }}>
                    {filteredItems.length === 0 ? (
                      <div style={{ padding: '1rem', textAlign: 'center', color: '#666' }}>
                        Товары не найдены
                      </div>
                    ) : (
                      filteredItems.map(item => (
                        <label key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}>
                          <input
                            type="checkbox"
                            checked={selectedItemIds.includes(item.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedItemIds([...selectedItemIds, item.id]);
                              } else {
                                setSelectedItemIds(selectedItemIds.filter(id => id !== item.id));
                              }
                            }}
                          />
                          <span><strong>{item.name}</strong> - {item.item_type} ({item.gender}) - {item.price} ¥</span>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button
                onClick={handleAddItemsToGroup}
                className="btn-primary"
                disabled={selectedItemIds.length === 0}
              >
                Добавить выбранные ({selectedItemIds.length})
              </button>
              <button onClick={() => setShowAddItemsModal(false)} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно изменения цены для всех товаров в группе */}
      {showPriceModal && (
        <div className="modal-overlay" onClick={() => setShowPriceModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Изменить цену для всех товаров в группе</h2>
              <button className="modal-close" onClick={() => setShowPriceModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Новая цена (¥) *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={newPrice}
                  onChange={(e) => setNewPrice(e.target.value)}
                  placeholder="Введите цену в юанях"
                  autoFocus
                />
                <small style={{ display: 'block', marginTop: '0.5rem', color: '#666' }}>
                  Цена будет изменена для всех {group?.items.length || 0} товаров в группе "{group?.name}"
                </small>
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={handleUpdateGroupPrice} className="btn-primary">
                Изменить цену
              </button>
              <button onClick={() => setShowPriceModal(false)} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно изменения сервисного сбора для всех товаров в группе */}
      {showServiceFeeModal && (
        <div className="modal-overlay" onClick={() => setShowServiceFeeModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Изменить сервисный сбор для всех товаров в группе</h2>
              <button className="modal-close" onClick={() => setShowServiceFeeModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Новый сервисный сбор (%) *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={newServiceFee}
                  onChange={(e) => setNewServiceFee(e.target.value)}
                  placeholder="Введите процент сервисного сбора"
                  autoFocus
                />
                <small style={{ display: 'block', marginTop: '0.5rem', color: '#666' }}>
                  Сервисный сбор будет изменен для всех {group?.items.length || 0} товаров в группе "{group?.name}"
                </small>
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={handleUpdateGroupServiceFee} className="btn-primary">
                Изменить сервисный сбор
              </button>
              <button onClick={() => setShowServiceFeeModal(false)} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно создания поста группы */}
      {showPostModal && postData && (
        <div className="modal-overlay" onClick={handleClosePostModal}>
          <div className="modal-content" style={{ maxWidth: '600px' }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Пост группы "{postData.group.name}"</h2>
              <button className="modal-close" onClick={handleClosePostModal}>×</button>
            </div>
            <div className="modal-body">
              {error && <div className="error-message">{error}</div>}
              {postData.photos.length > 0 && (
                <div className="form-group">
                  <label>Фото в пост (макс. 10). ↑↓ — порядок отправки</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem', alignItems: 'flex-start' }}>
                    {[
                      ...postPhotoIds.map((id) => postData.photos.find((p) => p.id === id)).filter(Boolean),
                      ...postData.photos.filter((p) => !postPhotoIds.includes(p.id)),
                    ].map((photo) => {
                      if (!photo) return null;
                      const isSelected = postPhotoIds.includes(photo.id);
                      const idx = postPhotoIds.indexOf(photo.id);
                      return (
                        <div key={photo.id} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px', opacity: isSelected ? 1 : 0.5 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <label style={{ cursor: postPhotoIds.length < 10 || isSelected ? 'pointer' : 'not-allowed' }}>
                              <input type="checkbox" checked={isSelected} onChange={() => togglePostPhoto(photo.id)} disabled={!isSelected && postPhotoIds.length >= 10} style={{ width: 16, height: 16, accentColor: '#4caf50' }} />
                              <img src={`/${photo.file_path}`} alt="" style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: '8px', marginLeft: 4, border: isSelected ? '2px solid #4caf50' : '2px solid transparent', display: 'block' }} />
                            </label>
                            {isSelected && (
                              <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <button type="button" onClick={() => movePostPhoto(idx, 'up')} disabled={idx === 0} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Выше">↑</button>
                                <button type="button" onClick={() => movePostPhoto(idx, 'down')} disabled={idx === postPhotoIds.length - 1} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Ниже">↓</button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {postData.photos.length === 0 && (
                <div className="error-message">Нет фото с telegram_file_id. Обновите фото в каталоге.</div>
              )}
              <div style={{ marginTop: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', color: '#666' }}>
                  Догрузить свои фото:
                </label>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/gif,image/webp"
                  multiple
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    setAdditionalPostFiles((prev) => {
                      const combined = [...prev, ...files];
                      if (combined.length + postPhotoIds.length > 10) {
                        return combined.slice(0, 10 - postPhotoIds.length);
                      }
                      return combined;
                    });
                    e.target.value = '';
                  }}
                  style={{ fontSize: '0.9rem' }}
                />
                {additionalPostFiles.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem', alignItems: 'flex-start' }}>
                    {additionalPostFiles.map((f, i) => (
                      <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', position: 'relative', border: '2px solid #4caf50', borderRadius: '8px', padding: '4px' }}>
                          <img src={URL.createObjectURL(f)} alt="" style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: '4px' }} />
                          <span style={{ fontSize: '0.75rem', maxWidth: 70, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</span>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <button type="button" onClick={() => moveAdditionalPhoto(i, 'up')} disabled={i === 0} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Выше">↑</button>
                            <button type="button" onClick={() => moveAdditionalPhoto(i, 'down')} disabled={i === additionalPostFiles.length - 1} style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: 1 }} title="Ниже">↓</button>
                          </div>
                          <button type="button" onClick={() => setAdditionalPostFiles((prev) => prev.filter((_, idx) => idx !== i))} style={{ position: 'absolute', top: 2, right: 2, background: '#f44336', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.7rem', padding: '2px 6px' }}>×</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <small style={{ display: 'block', marginTop: '0.25rem', color: '#666' }}>
                  Порядок: каталог (↑↓), затем свои фото (↑↓). Всего {postPhotoIds.length + additionalPostFiles.length} / 10
                </small>
              </div>
              <div className="form-group">
                <label>Текст поста (макс. {TELEGRAM_CAPTION_MAX_LENGTH} символов после форматирования)</label>
                <textarea
                  value={postText}
                  onChange={(e) => {
                    setPostText(e.target.value);
                    setError('');
                  }}
                  rows={14}
                  className="post-textarea"
                />
                <small className="char-count">{getTelegramCaptionLength(postText)} / {TELEGRAM_CAPTION_MAX_LENGTH}</small>
              </div>
            </div>
            <div className="modal-footer">
              <button
                onClick={handlePostToTelegram}
                className="btn-primary"
                disabled={posting || !postText.trim() || postPhotoIds.length === 0 || getTelegramCaptionLength(postText) > TELEGRAM_CAPTION_MAX_LENGTH || postPhotoIds.length + additionalPostFiles.length > 10}
              >
                {posting ? 'Отправка...' : '📢 Сделать пост в ТГК'}
              </button>
              <button onClick={handleClosePostModal} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ItemGroupDetail;



