import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { encodeUtf8Base64 } from '../../utils/sensitiveTransport';
import './Admins.css';

interface Admin {
  user_id: number;
  admin_type: string;
  role_id?: number | null;
  role_name?: string | null;
  role_title?: string | null;
  permissions?: Record<string, boolean> | null;
  login: string | null;
  tgid: number | null;
  vkid: number | null;
}

interface AdminRoleOption {
  id: number;
  name: string;
}

const Admins: React.FC = () => {
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Admin[]>([]);
  const [error, setError] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAdmins();
  }, []);

  const fetchAdmins = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/users/admin/admins');
      setAdmins(response.data);
      setError('');
    } catch (err: any) {
      if (err.response?.status === 403) {
        setError('Только владелец может просматривать администраторов');
      } else {
        setError(err.response?.data?.detail || 'Ошибка загрузки администраторов');
      }
      console.error('Ошибка загрузки администраторов:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query.length >= 1) {
      try {
        const response = await apiClient.get(`/users/admin/admins/search?q=${encodeURIComponent(query)}`);
        setSearchResults(response.data);
      } catch (err) {
        console.error('Ошибка поиска:', err);
        setSearchResults([]);
      }
    } else {
      setSearchResults([]);
    }
  };

  const handleDelete = async (userId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этого администратора?')) {
      return;
    }

    try {
      await apiClient.delete(`/users/admin/admins/${userId}`);
      setAdmins(admins.filter(a => a.user_id !== userId));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления администратора');
      console.error('Ошибка удаления:', err);
    }
  };

  const handleAdminClick = (userId: number) => {
    navigate(`/admins/${userId}`);
  };

  const displayAdmins = searchQuery && searchResults.length > 0 ? searchResults : admins;

  if (loading) {
    return <div className="admins-page">Загрузка...</div>;
  }

  if (error && !admins.length) {
    return (
      <div className="admins-page">
        <div className="error-message">{error}</div>
      </div>
    );
  }

  return (
    <div className="admins-page">
      <div className="admins-header">
        <h1>Администраторы</h1>
        <div className="header-actions">
          <Link to="/admin-roles" className="btn-view">
            Роли доступа
          </Link>
          <button type="button" onClick={fetchAdmins} className="btn-refresh">Обновить</button>
          <button type="button" onClick={() => setShowCreateForm(true)} className="btn-create">
            Создать админа
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {showCreateForm && (
        <CreateAdminForm
          onClose={() => setShowCreateForm(false)}
          onSuccess={() => {
            setShowCreateForm(false);
            fetchAdmins();
          }}
        />
      )}

      <div className="search-box">
        <input
          type="text"
          placeholder="Поиск по ID, TG ID или VK ID..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          className="search-input"
        />
      </div>

      {/* Таблица для десктопа */}
      <div className="admins-table-container">
        <table className="admins-table">
          <thead>
            <tr>
              <th>Внутренний ID</th>
              <th>TG ID</th>
              <th>VK ID</th>
              <th>Тип</th>
              <th>Должность</th>
              <th>Логин</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {displayAdmins.length === 0 ? (
              <tr>
                <td colSpan={7} className="no-data">Администраторы не найдены</td>
              </tr>
            ) : (
              displayAdmins.map((admin) => (
                <tr key={admin.user_id}>
                  <td>{admin.user_id}</td>
                  <td>{admin.tgid || '-'}</td>
                  <td>{admin.vkid || '-'}</td>
                  <td>
                    <span className={`admin-type admin-type-${admin.admin_type}`}>
                      {admin.admin_type === 'owner' ? 'owner' : admin.admin_type}
                    </span>
                  </td>
                  <td>
                    {admin.admin_type === 'owner'
                      ? 'Владелец'
                      : admin.role_name || admin.role_title || '—'}
                  </td>
                  <td>{admin.login || '-'}</td>
                  <td>
                    <button
                      onClick={() => handleAdminClick(admin.user_id)}
                      className="btn-view"
                    >
                      Просмотр
                    </button>
                    {admin.admin_type !== 'owner' && (
                      <button
                        onClick={() => handleDelete(admin.user_id)}
                        className="btn-delete"
                      >
                        Удалить
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Карточки для мобильных */}
      <div className="admins-cards-container">
        {displayAdmins.length === 0 ? (
          <div className="no-data">Администраторы не найдены</div>
        ) : (
          displayAdmins.map((admin) => (
            <div key={admin.user_id} className="admin-card">
              <div className="admin-card-header">
                <h3>Администратор #{admin.user_id}</h3>
                <span className={`admin-type admin-type-${admin.admin_type}`}>
                  {admin.admin_type === 'owner' ? 'owner' : admin.admin_type}
                </span>
              </div>
              <div className="admin-card-body">
                <div className="admin-card-field">
                  <label>Должность:</label>
                  <div>
                    {admin.admin_type === 'owner'
                      ? 'Владелец'
                      : admin.role_name || admin.role_title || '—'}
                  </div>
                </div>
                <div className="admin-card-field">
                  <label>TG ID:</label>
                  <div>{admin.tgid || '-'}</div>
                </div>
                <div className="admin-card-field">
                  <label>VK ID:</label>
                  <div>{admin.vkid || '-'}</div>
                </div>
                <div className="admin-card-field">
                  <label>Логин:</label>
                  <div>{admin.login || '-'}</div>
                </div>
                <div className="admin-card-actions">
                  <button
                    onClick={() => handleAdminClick(admin.user_id)}
                    className="btn-view"
                  >
                    Просмотр
                  </button>
                  {admin.admin_type !== 'owner' && (
                    <button
                      onClick={() => handleDelete(admin.user_id)}
                      className="btn-delete"
                    >
                      Удалить
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

interface CreateAdminFormProps {
  onClose: () => void;
  onSuccess: () => void;
}

const CreateAdminForm: React.FC<CreateAdminFormProps> = ({ onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    searchQuery: '',
    selectedUser: null as { id: number; tgid: number | null; vkid: number | null; gender: string | null } | null,
    roleId: '' as number | '',
    login: '',
    password: '',
  });
  const [roles, setRoles] = useState<AdminRoleOption[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get<AdminRoleOption[]>('/users/admin/roles');
        if (cancelled) return;
        setRoles(res.data);
        if (res.data.length === 1) {
          setFormData((f) => ({ ...f, roleId: res.data[0].id }));
        }
      } catch (e) {
        console.error(e);
        if (!cancelled) setError('Не удалось загрузить роли (создайте их в «Роли доступа»)');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSearch = async () => {
    const query = formData.searchQuery.trim();
    
    if (query.length < 1) {
      setError('Введите ID, TG ID или VK ID для поиска');
      return;
    }

    try {
      setSearchLoading(true);
      setError('');
      const response = await apiClient.get(`/users/admin/users/search?q=${encodeURIComponent(query)}`);
      setSearchResults(response.data);
      if (response.data.length > 0) {
        setShowResults(true);
      } else {
        setError('Пользователи не найдены');
        setShowResults(false);
      }
    } catch (err: any) {
      console.error('Ошибка поиска:', err);
      // Правильно обрабатываем ошибку - извлекаем строку из объекта
      let errorMessage = 'Ошибка поиска пользователей';
      if (err.response?.data) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        } else if (err.response.data.detail && typeof err.response.data.detail === 'object') {
          // Если detail это объект (например, валидационная ошибка), преобразуем в строку
          errorMessage = JSON.stringify(err.response.data.detail);
        } else if (typeof err.response.data === 'string') {
          errorMessage = err.response.data;
        }
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setSearchResults([]);
      setShowResults(false);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSelectUser = (user: any) => {
    setFormData({
      ...formData,
      selectedUser: user,
      searchQuery: `ID: ${user.id}${user.tgid ? ` | TG: ${user.tgid}` : ''}${user.vkid ? ` | VK: ${user.vkid}` : ''}`,
    });
    setShowResults(false);
    setSearchResults([]);
  };

  const handleSearchKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSearch();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    if (!formData.selectedUser) {
      setError('Необходимо выбрать пользователя из списка');
      return;
    }
    if (formData.roleId === '') {
      setError('Выберите роль доступа');
      return;
    }

    setLoading(true);

    try {
      const payload = {
        user_id: formData.selectedUser.id,
        role_id: formData.roleId,
        login: formData.login,
        password: encodeUtf8Base64(formData.password),
      };

      await apiClient.post('/users/admin/admins', payload);
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания администратора');
    } finally {
      setLoading(false);
    }
  };

  // Закрытие выпадающего списка при клике вне его
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.search-wrapper')) {
        setShowResults(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Создать администратора</h2>
          <button type="button" onClick={onClose} className="modal-close" aria-label="Закрыть">&times;</button>
        </div>
        <form onSubmit={handleSubmit} autoComplete="off">
          <input type="text" name="fakeuser" autoComplete="username" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden readOnly />
          <input type="password" name="fakepass" autoComplete="new-password" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden readOnly />
          <div className="form-group">
            <label>Поиск пользователя (ID / TG ID / VK ID):</label>
            <div className="search-wrapper">
              <div className="search-input-group">
                <input
                  type="search"
                  name="timoshka-user-search"
                  placeholder="Введите ID, TG ID или VK ID..."
                  value={formData.searchQuery}
                  onChange={(e) => {
                    setFormData({ ...formData, searchQuery: e.target.value, selectedUser: null });
                    setShowResults(false);
                    setError('');
                  }}
                  onKeyPress={handleSearchKeyPress}
                  autoComplete="off"
                  disabled={!!formData.selectedUser}
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={searchLoading || !!formData.selectedUser || !formData.searchQuery.trim()}
                  className="btn-search"
                >
                  {searchLoading ? 'Поиск...' : 'Поиск'}
                </button>
                {formData.selectedUser && (
                  <button
                    type="button"
                    onClick={() => {
                      setFormData({ ...formData, searchQuery: '', selectedUser: null });
                      setShowResults(false);
                    }}
                    className="btn-clear-search"
                  >
                    ✕
                  </button>
                )}
              </div>
              {showResults && searchResults.length > 0 && (
                <div className="search-results">
                  {searchResults.map((user) => (
                    <div
                      key={user.id}
                      className="search-result-item"
                      onClick={() => handleSelectUser(user)}
                    >
                      <div>
                        <strong>ID:</strong> {user.id}
                        {user.tgid && <span> | <strong>TG:</strong> {user.tgid}</span>}
                        {user.vkid && <span> | <strong>VK:</strong> {user.vkid}</span>}
                      </div>
                      {user.gender && (
                        <div className="search-result-gender">
                          {user.gender === 'male' ? 'Мужской' : user.gender === 'female' ? 'Женский' : user.gender}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {formData.selectedUser && (
              <div className="selected-user-info">
                <strong>Выбран пользователь:</strong> ID: {formData.selectedUser.id}
                {formData.selectedUser.tgid && ` | TG: ${formData.selectedUser.tgid}`}
                {formData.selectedUser.vkid && ` | VK: ${formData.selectedUser.vkid}`}
              </div>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="create-admin-role-select">Роль доступа</label>
            <select
              id="create-admin-role-select"
              value={formData.roleId === '' ? '' : String(formData.roleId)}
              onChange={(e) => {
                const v = e.target.value;
                setFormData({ ...formData, roleId: v === '' ? '' : Number(v) });
              }}
              required
            >
              <option value="">— выберите роль —</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.35rem' }}>
              Наборы прав настраиваются в разделе «Роли доступа».
            </p>
          </div>
          <div className="form-group">
            <label htmlFor="create-staff-login">Логин для входа в админку</label>
            <input
              id="create-staff-login"
              type="text"
              name="timoshka-staff-login"
              autoComplete="off"
              value={formData.login}
              onChange={(e) => setFormData({ ...formData, login: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="create-staff-password">Пароль</label>
            <input
              id="create-staff-password"
              type="password"
              name="timoshka-staff-password"
              autoComplete="new-password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              required
            />
          </div>
          {error && <div className="error-message">{error}</div>}
          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn-cancel">
              Отмена
            </button>
            <button type="submit" disabled={loading} className="btn-submit">
              {loading ? 'Создание...' : 'Создать'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Admins;
