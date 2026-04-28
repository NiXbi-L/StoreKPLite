import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Catalog.css';

interface ItemType {
  id: number;
  name: string;
  created_at: string;
}

const ItemTypes: React.FC = () => {
  const [types, setTypes] = useState<ItemType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingType, setEditingType] = useState<ItemType | null>(null);
  const [newTypeName, setNewTypeName] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchTypes();
  }, []);

  const fetchTypes = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/products/admin/item-types');
      console.log('Получены типы:', response.data);
      setTypes(response.data || []);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки типов');
      console.error('Ошибка загрузки типов:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateType = async () => {
    if (!newTypeName.trim()) {
      setError('Название типа не может быть пустым');
      return;
    }

    try {
      await apiClient.post('/products/admin/item-types', { name: newTypeName.trim() });
      setShowCreateModal(false);
      setNewTypeName('');
      await fetchTypes();
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания типа');
      console.error('Ошибка создания типа:', err);
    }
  };

  const handleEditType = async () => {
    if (!editingType || !newTypeName.trim()) {
      setError('Название типа не может быть пустым');
      return;
    }

    try {
      await apiClient.put(`/products/admin/item-types/${editingType.id}`, { name: newTypeName.trim() });
      setShowEditModal(false);
      setEditingType(null);
      setNewTypeName('');
      await fetchTypes();
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления типа');
      console.error('Ошибка обновления типа:', err);
    }
  };

  const handleDeleteType = async (typeId: number) => {
    const type = types.find(t => t.id === typeId);
    if (!window.confirm(`Вы уверены, что хотите удалить тип "${type?.name}"? Это действие невозможно отменить, если тип используется в товарах.`)) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/item-types/${typeId}`);
      await fetchTypes();
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления типа');
      console.error('Ошибка удаления типа:', err);
    }
  };

  const openEditModal = (type: ItemType) => {
    setEditingType(type);
    setNewTypeName(type.name);
    setShowEditModal(true);
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return dateString;
      }
      return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return dateString;
    }
  };

  if (loading) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  return (
    <div className="catalog-page item-types-page">
      <div className="catalog-header">
        <h1>Типы товаров</h1>
        <button
          className="btn btn-primary"
          onClick={() => {
            setNewTypeName('');
            setShowCreateModal(true);
          }}
        >
          + Создать тип
        </button>
      </div>

      {error && (
        <div className="error-message" style={{ margin: '10px 0', padding: '10px', background: '#fee', color: '#c00', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      <div className="catalog-list">
        {types.length === 0 ? (
          <div className="no-data">Типы товаров не найдены</div>
        ) : (
          <div className="item-types-grid">
            {types.map((type) => (
              <div key={type.id} className="catalog-card">
                <div className="catalog-card-header">
                  <h3>{type.name}</h3>
                  <div className="catalog-card-id">#{type.id}</div>
                </div>
                <div className="catalog-card-body">
                  <div className="catalog-card-field">
                    <label>Создан:</label>
                    <div>{formatDate(type.created_at)}</div>
                  </div>
                </div>
                <div className="catalog-card-actions">
                  <button
                    className="btn btn-secondary"
                    onClick={() => openEditModal(type)}
                  >
                    Редактировать
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleDeleteType(type.id)}
                  >
                    Удалить
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Модальное окно создания */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Создать тип товара</h2>
            <div className="form-group">
              <label>Название типа:</label>
              <input
                type="text"
                value={newTypeName}
                onChange={(e) => setNewTypeName(e.target.value)}
                placeholder="Например: Футболки"
                autoFocus
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleCreateType();
                  }
                }}
              />
            </div>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleCreateType}>
                Создать
              </button>
              <button className="btn btn-secondary" onClick={() => {
                setShowCreateModal(false);
                setNewTypeName('');
              }}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно редактирования */}
      {showEditModal && editingType && (
        <div className="modal-overlay" onClick={() => {
          setShowEditModal(false);
          setEditingType(null);
          setNewTypeName('');
        }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Редактировать тип товара</h2>
            <div className="form-group">
              <label>Название типа:</label>
              <input
                type="text"
                value={newTypeName}
                onChange={(e) => setNewTypeName(e.target.value)}
                placeholder="Например: Футболки"
                autoFocus
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleEditType();
                  }
                }}
              />
            </div>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleEditType}>
                Сохранить
              </button>
              <button className="btn btn-secondary" onClick={() => {
                setShowEditModal(false);
                setEditingType(null);
                setNewTypeName('');
              }}>
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ItemTypes;
