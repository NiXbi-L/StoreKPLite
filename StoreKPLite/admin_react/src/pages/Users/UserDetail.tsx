import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Users.css';

interface User {
  id: number;
  tgid: number | null;
  vkid: number | null;
  gender: string | null;
  privacy_policy_accepted: boolean;
  created_at: string;
}

const UserDetail: React.FC = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (userId) {
      fetchUser(parseInt(userId));
    }
  }, [userId]);

  const fetchUser = async (id: number) => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/users/admin/users/${id}`);
      setUser(response.data);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Пользователь не найден');
      console.error('Ошибка загрузки пользователя:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!user || !window.confirm('Вы уверены, что хотите удалить этого пользователя?')) {
      return;
    }

    try {
      await apiClient.delete(`/users/admin/users/${user.id}`);
      navigate('/users');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления пользователя');
      console.error('Ошибка удаления:', err);
    }
  };

  if (loading) {
    return <div className="users-page">Загрузка...</div>;
  }

  if (error && !user) {
    return (
      <div className="users-page">
        <div className="error-message">{error}</div>
        <button onClick={() => navigate('/users')} className="btn-view">
          Назад к списку
        </button>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="users-page">
      <h1>Пользователь #{user.id}</h1>

      {error && <div className="error-message">{error}</div>}

      <div className="user-detail-card">
        <div className="detail-row">
          <label>Внутренний ID:</label>
          <div>{user.id}</div>
        </div>
        <div className="detail-row">
          <label>Telegram ID:</label>
          <div>{user.tgid || 'Не указан'}</div>
        </div>
        <div className="detail-row">
          <label>VK ID:</label>
          <div>{user.vkid || 'Не указан'}</div>
        </div>
        <div className="detail-row">
          <label>Пол:</label>
          <div>
            {user.gender === 'male' ? 'Мужской' : user.gender === 'female' ? 'Женский' : 'Не указан'}
          </div>
        </div>
        <div className="detail-row">
          <label>Политика конфиденциальности:</label>
          <div>{user.privacy_policy_accepted ? 'Принята' : 'Не принята'}</div>
        </div>
        <div className="detail-row">
          <label>Дата создания:</label>
          <div>{new Date(user.created_at).toLocaleString('ru-RU')}</div>
        </div>
      </div>

      <div className="detail-actions">
        <button onClick={() => navigate('/users')} className="btn-view">
          Назад к списку
        </button>
        <button onClick={handleDelete} className="btn-delete">
          Удалить пользователя
        </button>
      </div>
    </div>
  );
};

export default UserDetail;
