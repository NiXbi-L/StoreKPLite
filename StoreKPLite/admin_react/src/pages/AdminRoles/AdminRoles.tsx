import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import '../Admins/Admins.css';

interface PermissionItem {
  key: string;
  label: string;
}

interface AdminRoleRow {
  id: number;
  name: string;
  permissions: Record<string, boolean>;
}

function emptyPermissionsFromCatalog(catalog: PermissionItem[]): Record<string, boolean> {
  const o: Record<string, boolean> = {};
  catalog.forEach((c) => {
    o[c.key] = false;
  });
  return o;
}

const AdminRoles: React.FC = () => {
  const [roles, setRoles] = useState<AdminRoleRow[]>([]);
  const [catalog, setCatalog] = useState<PermissionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState<null | { mode: 'create' } | { mode: 'edit'; role: AdminRoleRow }>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const [r, c] = await Promise.all([
        apiClient.get<AdminRoleRow[]>('/users/admin/roles'),
        apiClient.get<PermissionItem[]>('/users/admin/permission-catalog'),
      ]);
      setRoles(r.data);
      setCatalog(c.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Не удалось загрузить роли');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id: number, name: string) => {
    if (!window.confirm(`Удалить роль «${name}»? (Только если ни у кого не назначена.)`)) return;
    try {
      await apiClient.delete(`/users/admin/roles/${id}`);
      await load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Ошибка удаления');
    }
  };

  if (loading && !roles.length) {
    return <div className="admins-page">Загрузка...</div>;
  }

  return (
    <div className="admins-page">
      <div className="admins-header">
        <h1>Роли доступа</h1>
        <div className="header-actions">
          <Link to="/admins" className="btn-view">
            К сотрудникам
          </Link>
          <button type="button" className="btn-refresh" onClick={load}>
            Обновить
          </button>
          <button
            type="button"
            className="btn-create"
            onClick={() => setModal({ mode: 'create' })}
            disabled={!catalog.length}
          >
            Новая роль
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <p style={{ color: '#666', marginBottom: '1rem', maxWidth: '640px' }}>
        Здесь задаются наборы прав. У каждого сотрудника в разделе «Администраторы» выбирается одна роль. Изменение роли
        сразу меняет права у всех, у кого она назначена (после следующего входа в админку).
      </p>

      <div className="admins-table-container">
        <table className="admins-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {roles.length === 0 ? (
              <tr>
                <td colSpan={3} className="no-data">
                  Ролей пока нет (после обновления бэкенда появятся стандартные три роли)
                </td>
              </tr>
            ) : (
              roles.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.name}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-view"
                      onClick={() => setModal({ mode: 'edit', role: row })}
                    >
                      Правки
                    </button>
                    <button type="button" className="btn-delete" onClick={() => handleDelete(row.id, row.name)}>
                      Удалить
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {modal && catalog.length > 0 && (
        <RoleModal
          catalog={catalog}
          mode={modal.mode}
          role={modal.mode === 'edit' ? modal.role : undefined}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </div>
  );
};

interface RoleModalProps {
  catalog: PermissionItem[];
  mode: 'create' | 'edit';
  role?: AdminRoleRow;
  onClose: () => void;
  onSaved: () => void;
}

const RoleModal: React.FC<RoleModalProps> = ({ catalog, mode, role, onClose, onSaved }) => {
  const [name, setName] = useState(role?.name || '');
  const [permissions, setPermissions] = useState<Record<string, boolean>>(() =>
    role?.permissions ? { ...role.permissions } : emptyPermissionsFromCatalog(catalog)
  );
  const [err, setErr] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    const n = name.trim();
    if (!n) {
      setErr('Введите название роли');
      return;
    }
    setSaving(true);
    try {
      if (mode === 'create') {
        await apiClient.post('/users/admin/roles', { name: n, permissions });
      } else if (role) {
        await apiClient.put(`/users/admin/roles/${role.id}`, { name: n, permissions });
      }
      onSaved();
    } catch (e: any) {
      setErr(e.response?.data?.detail || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{mode === 'create' ? 'Новая роль' : 'Редактировать роль'}</h2>
          <button type="button" onClick={onClose} className="modal-close" aria-label="Закрыть">
            &times;
          </button>
        </div>
        {/* Ловушка для менеджера паролей: не подставлять логин владельца в название роли */}
        <form autoComplete="off" onSubmit={submit}>
          <input type="text" name="fakeuser" autoComplete="username" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden="true" readOnly />
          <input type="password" name="fakepass" autoComplete="new-password" tabIndex={-1} style={{ position: 'absolute', opacity: 0, height: 0, width: 0 }} aria-hidden="true" readOnly />
          <div className="form-group">
            <label htmlFor="admin-role-name-input">Название роли</label>
            <input
              id="admin-role-name-input"
              type="text"
              name="timoshka-admin-role-name"
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>Права</label>
            <div className="permissions-toggles">
              {catalog.map((item) => (
                <label
                  key={item.key}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}
                >
                  <input
                    type="checkbox"
                    checked={Boolean(permissions[item.key])}
                    onChange={(e) => setPermissions((p) => ({ ...p, [item.key]: e.target.checked }))}
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>
          {err && <div className="error-message">{err}</div>}
          <div className="form-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="btn-submit" disabled={saving}>
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AdminRoles;
