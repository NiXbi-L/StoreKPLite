import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Users.css';

const PAGE_SIZE = 50;

interface User {
  id: number;
  tgid: number | null;
  firstname?: string | null;
  username?: string | null;
  gender: string | null;
  privacy_policy_accepted: boolean;
  created_at: string;
}

interface AdminUserListPayload {
  items: User[];
  total: number;
  has_more: boolean;
}

const Users: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [filterQ, setFilterQ] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setFilterQ((prev) => (prev === searchInput ? prev : searchInput));
    }, 400);
    return () => clearTimeout(t);
  }, [searchInput]);

  const fetchUsersPage = useCallback(
    async (skip: number, append: boolean) => {
      try {
        if (!append) setLoading(true);
        else setLoadingMore(true);
        const params = new URLSearchParams();
        params.set('skip', String(skip));
        params.set('limit', String(PAGE_SIZE));
        const q = filterQ.trim();
        if (q) params.set('q', q);

        const response = await apiClient.get<AdminUserListPayload>(`/users/admin/users?${params.toString()}`);
        const { items, total, has_more } = response.data;
        if (append) {
          setUsers((prev) => [...prev, ...items]);
        } else {
          setUsers(items);
        }
        setTotalCount(total);
        setHasMore(Boolean(has_more));
        setError('');
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Ошибка загрузки пользователей');
        console.error('Ошибка загрузки пользователей:', err);
        if (!append) setUsers([]);
        setHasMore(false);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [filterQ],
  );

  useEffect(() => {
    fetchUsersPage(0, false);
  }, [fetchUsersPage]);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore || loading) return;
    fetchUsersPage(users.length, true);
  }, [hasMore, loadingMore, loading, users.length, fetchUsersPage]);

  useEffect(() => {
    if (!hasMore || loadingMore || loading) return;
    const el = loadMoreSentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: '200px', threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, loadMore]);

  const handleDelete = async (userId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этого пользователя?')) {
      return;
    }

    try {
      await apiClient.delete(`/users/admin/users/${userId}`);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setTotalCount((c) => Math.max(0, c - 1));
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления пользователя');
      console.error('Ошибка удаления:', err);
    }
  };

  const handleUserClick = (userId: number) => {
    navigate(`/users/${userId}`);
  };

  if (loading && users.length === 0) {
    return <div className="users-page">Загрузка...</div>;
  }

  return (
    <div className="users-page">
      <div className="users-header">
        <h1>Пользователи</h1>
        <button onClick={() => fetchUsersPage(0, false)} className="btn-refresh">
          Обновить
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="search-box">
        <input
          type="text"
          placeholder="Фильтр: id, TG id, @username, имя…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="search-input"
        />
      </div>

      <p className="users-total-hint">
        Найдено: {totalCount}
        {loadingMore ? ' · загрузка…' : ''}
      </p>

      <div className="users-table-container">
        <table className="users-table">
          <thead>
            <tr>
              <th>Внутренний ID</th>
              <th>TG ID</th>
              <th>Имя</th>
              <th>Username</th>
              <th>Пол</th>
              <th>Политика принята</th>
              <th>Дата создания</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={8} className="no-data">
                  Пользователи не найдены
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id}>
                  <td>{user.id}</td>
                  <td>{user.tgid ?? '—'}</td>
                  <td>{user.firstname?.trim() || '—'}</td>
                  <td>{user.username ? `@${user.username}` : '—'}</td>
                  <td>{user.gender === 'male' ? 'Мужской' : user.gender === 'female' ? 'Женский' : '—'}</td>
                  <td>{user.privacy_policy_accepted ? 'Да' : 'Нет'}</td>
                  <td>{new Date(user.created_at).toLocaleString('ru-RU')}</td>
                  <td>
                    <button onClick={() => handleUserClick(user.id)} className="btn-view">
                      Просмотр
                    </button>
                    <button onClick={() => handleDelete(user.id)} className="btn-delete">
                      Удалить
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="users-cards-container">
        {users.length === 0 ? (
          <div className="no-data">Пользователи не найдены</div>
        ) : (
          users.map((user) => (
            <div key={user.id} className="user-card">
              <div className="user-card-header">
                <h3>Пользователь #{user.id}</h3>
              </div>
              <div className="user-card-body">
                <div className="user-card-field">
                  <label>TG ID:</label>
                  <div>{user.tgid ?? '—'}</div>
                </div>
                <div className="user-card-field">
                  <label>Имя:</label>
                  <div>{user.firstname?.trim() || '—'}</div>
                </div>
                <div className="user-card-field">
                  <label>Username:</label>
                  <div>{user.username ? `@${user.username}` : '—'}</div>
                </div>
                <div className="user-card-field">
                  <label>Пол:</label>
                  <div>{user.gender === 'male' ? 'Мужской' : user.gender === 'female' ? 'Женский' : '—'}</div>
                </div>
                <div className="user-card-field">
                  <label>Политика принята:</label>
                  <div>{user.privacy_policy_accepted ? 'Да' : 'Нет'}</div>
                </div>
                <div className="user-card-field">
                  <label>Дата создания:</label>
                  <div>{new Date(user.created_at).toLocaleString('ru-RU')}</div>
                </div>
                <div className="user-card-actions">
                  <button onClick={() => handleUserClick(user.id)} className="btn-view">
                    Просмотр
                  </button>
                  <button onClick={() => handleDelete(user.id)} className="btn-delete">
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {hasMore && <div ref={loadMoreSentinelRef} className="users-load-sentinel" aria-hidden="true" />}
    </div>
  );
};

export default Users;
