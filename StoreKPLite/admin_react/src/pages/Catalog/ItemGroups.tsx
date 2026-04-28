import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Catalog.css';

interface ItemGroup {
  id: number;
  name: string;
  created_at: string;
  items_count?: number;
}


const ItemGroups: React.FC = () => {
  const [groups, setGroups] = useState<ItemGroup[]>([]);
  const [filteredGroups, setFilteredGroups] = useState<ItemGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchGroups();
  }, []);

  // Фильтрация групп по поисковому запросу
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredGroups(groups);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = groups.filter(group =>
        group.name.toLowerCase().includes(query) ||
        String(group.id).includes(query)
      );
      setFilteredGroups(filtered);
    }
  }, [searchQuery, groups]);

  const fetchGroups = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/products/admin/item-groups');
      console.log('Получены группы:', response.data);
      console.log('Количество групп:', response.data?.length);
      setGroups(response.data || []);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки групп');
      console.error('Ошибка загрузки групп:', err);
      console.error('Детали ошибки:', err.response?.data);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      setError('Название группы не может быть пустым');
      return;
    }

    try {
      await apiClient.post('/products/admin/item-groups', { name: newGroupName });
      setShowCreateModal(false);
      setNewGroupName('');
      await fetchGroups();
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания группы');
      console.error('Ошибка создания группы:', err);
    }
  };


  const handleDeleteGroup = async (groupId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить эту группу? Товары останутся, но будут без группы.')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/item-groups/${groupId}`);
      await fetchGroups();
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления группы');
      console.error('Ошибка удаления группы:', err);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return dateString; // Возвращаем исходную строку, если дата невалидна
      }
      return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return dateString; // Возвращаем исходную строку при ошибке
    }
  };

  if (loading) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  return (
    <div className="catalog-page item-groups-page">
      <div className="catalog-header">
        <h1>Группы товаров</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button onClick={() => navigate('/catalog')} className="btn-secondary">
            Назад к каталогу
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary">
            Создать группу
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {/* Поиск по названию */}
      <div className="catalog-filters" style={{ marginTop: '1rem' }}>
        <div className="filter-group">
          <label>Поиск по названию:</label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Введите название группы или ID..."
          />
        </div>
        {searchQuery && (
          <div style={{ alignSelf: 'flex-end', padding: '0.5rem', color: '#666' }}>
            Найдено: {filteredGroups.length} из {groups.length}
          </div>
        )}
      </div>

      <div style={{ marginTop: '2rem' }}>
        <h2>Список групп ({searchQuery ? filteredGroups.length : groups.length})</h2>
        {!Array.isArray(groups) ? (
          <div className="error-message">Ошибка: данные не являются массивом</div>
        ) : (searchQuery ? filteredGroups : groups).length === 0 ? (
          <div className="no-data">{searchQuery ? 'Группы не найдены' : 'Групп пока нет'}</div>
        ) : (
          <div className="catalog-cards-container">
            {(searchQuery ? filteredGroups : groups).map((group) => (
              <div
                key={group.id}
                className="catalog-card"
                onClick={() => navigate(`/catalog/groups/${group.id}`)}
                style={{ cursor: 'pointer' }}
              >
                <div className="catalog-card-header">
                  <h3>{group.name}</h3>
                  <div className="catalog-card-id">#{group.id}</div>
                </div>
                <div className="catalog-card-body">
                  <div className="catalog-card-field">
                    <label>Товаров в группе:</label>
                    <div><strong>{group.items_count || 0}</strong></div>
                  </div>
                  <div className="catalog-card-field">
                    <label>Создана:</label>
                    <div>{formatDate(group.created_at)}</div>
                  </div>
                  <div className="catalog-card-actions">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/catalog/groups/${group.id}`);
                      }}
                      className="btn-view"
                    >
                      Открыть
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteGroup(group.id);
                      }}
                      className="btn-delete"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Модальное окно создания группы */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Создать группу</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Название группы *</label>
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="Например: Кроссовки Nike в разных цветах"
                  autoFocus
                />
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={handleCreateGroup} className="btn-primary">
                Создать
              </button>
              <button onClick={() => setShowCreateModal(false)} className="btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default ItemGroups;

