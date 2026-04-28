import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { encodeUtf8Base64 } from '../../utils/sensitiveTransport';
import './Admins.css';

interface PermissionCatalogItem {
  key: string;
  label: string;
}

interface AdminRoleOption {
  id: number;
  name: string;
}

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

const AdminDetail: React.FC = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showEditForm, setShowEditForm] = useState(false);
  const [permissionLabels, setPermissionLabels] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get<PermissionCatalogItem[]>('/users/admin/permission-catalog');
        if (cancelled) return;
        const m: Record<string, string> = {};
        res.data.forEach((i) => {
          m[i.key] = i.label;
        });
        setPermissionLabels(m);
      } catch {
        /* без подписей */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (userId) {
      fetchAdmin(parseInt(userId, 10));
    }
  }, [userId]);

  const fetchAdmin = async (id: number) => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/users/admin/admins/${id}`);
      setAdmin(response.data);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Администратор не найден');
      console.error('Ошибка загрузки администратора:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!admin || !window.confirm('Вы уверены, что хотите удалить этого администратора?')) {
      return;
    }

    try {
      await apiClient.delete(`/users/admin/admins/${admin.user_id}`);
      navigate('/admins');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления администратора');
      console.error('Ошибка удаления:', err);
    }
  };

  if (loading) {
    return <div className="admins-page">Загрузка...</div>;
  }

  if (error && !admin) {
    return (
      <div className="admins-page">
        <div className="error-message">{error}</div>
        <button type="button" onClick={() => navigate('/admins')} className="btn-view">
          Назад к списку
        </button>
      </div>
    );
  }

  if (!admin) {
    return null;
  }

  const isOwnerRow = admin.admin_type === 'owner';

  return (
    <div className="admins-page">
      <h1>Администратор #{admin.user_id}</h1>

      {error && <div className="error-message">{error}</div>}

      {showEditForm && !isOwnerRow && (
        <EditAdminForm
          admin={admin}
          onClose={() => setShowEditForm(false)}
          onSuccess={() => {
            setShowEditForm(false);
            fetchAdmin(admin.user_id);
          }}
        />
      )}

      <div className="admin-detail-card">
        <div className="detail-row">
          <label>Внутренний ID:</label>
          <div>{admin.user_id}</div>
        </div>
        <div className="detail-row">
          <label>Telegram ID:</label>
          <div>{admin.tgid || 'Не указан'}</div>
        </div>
        <div className="detail-row">
          <label>VK ID:</label>
          <div>{admin.vkid || 'Не указан'}</div>
        </div>
        <div className="detail-row">
          <label>Тип записи:</label>
          <div>
            <span className={`admin-type admin-type-${admin.admin_type}`}>
              {isOwnerRow ? 'owner' : admin.admin_type}
            </span>
          </div>
        </div>
        <div className="detail-row">
          <label>Роль:</label>
          <div>{isOwnerRow ? 'Владелец' : admin.role_name || admin.role_title || '—'}</div>
        </div>
        {admin.role_id != null && !isOwnerRow && (
          <div className="detail-row">
            <label>ID роли:</label>
            <div>{admin.role_id}</div>
          </div>
        )}
        <div className="detail-row">
          <label>Логин:</label>
          <div>{admin.login || 'Не установлен'}</div>
        </div>
        {!isOwnerRow && admin.permissions && (
          <div className="detail-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <label>Эффективные права (из роли):</label>
            <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
              {Object.entries(admin.permissions)
                .filter(([, v]) => v)
                .map(([k]) => (
                  <li key={k}>{permissionLabels[k] || k}</li>
                ))}
            </ul>
          </div>
        )}
      </div>

      <div className="detail-actions">
        <button type="button" onClick={() => navigate('/admins')} className="btn-view">
          Назад к списку
        </button>
        {!isOwnerRow && (
          <>
            <button type="button" onClick={() => setShowEditForm(true)} className="btn-create">
              Редактировать
            </button>
            <button type="button" onClick={handleDelete} className="btn-delete">
              Удалить администратора
            </button>
          </>
        )}
      </div>
    </div>
  );
};

interface EditAdminFormProps {
  admin: Admin;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAdminForm: React.FC<EditAdminFormProps> = ({ admin, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    roleId: admin.role_id != null ? admin.role_id : ('' as number | ''),
    login: admin.login || '',
    password: '',
  });
  const [roles, setRoles] = useState<AdminRoleOption[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get<AdminRoleOption[]>('/users/admin/roles');
        if (cancelled) return;
        setRoles(res.data);
      } catch (e) {
        console.error(e);
        if (!cancelled) setError('Не удалось загрузить список ролей');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (formData.roleId === '') {
      setError('Выберите роль');
      return;
    }
    setLoading(true);

    try {
      const payload: { role_id: number; login?: string | null; password?: string } = {
        role_id: formData.roleId as number,
      };
      if (formData.login !== (admin.login || '')) {
        payload.login = formData.login || null;
      }
      if (formData.password) {
        payload.password = encodeUtf8Base64(formData.password);
      }

      await apiClient.put(`/users/admin/admins/${admin.user_id}`, payload);
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления администратора');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Редактировать сотрудника</h2>
          <button type="button" onClick={onClose} className="modal-close" aria-label="Закрыть">
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit} autoComplete="off">
          <input type="text" name="fakeuser" autoComplete="username" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden readOnly />
          <input type="password" name="fakepass" autoComplete="new-password" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden readOnly />
          <div className="form-group">
            <label htmlFor="edit-admin-role">Роль доступа</label>
            <select
              id="edit-admin-role"
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
          </div>
          <div className="form-group">
            <label htmlFor="edit-staff-login">Логин</label>
            <input
              id="edit-staff-login"
              type="text"
              name="timoshka-edit-staff-login"
              autoComplete="off"
              value={formData.login}
              onChange={(e) => setFormData({ ...formData, login: e.target.value })}
              placeholder="Оставьте пустым, чтобы удалить логин"
            />
          </div>
          <div className="form-group">
            <label htmlFor="edit-staff-password">Новый пароль</label>
            <input
              id="edit-staff-password"
              type="password"
              name="timoshka-edit-staff-password"
              autoComplete="new-password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="Оставьте пустым, чтобы не менять пароль"
            />
          </div>
          {error && <div className="error-message">{error}</div>}
          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn-cancel">
              Отмена
            </button>
            <button type="submit" disabled={loading} className="btn-submit">
              {loading ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AdminDetail;
