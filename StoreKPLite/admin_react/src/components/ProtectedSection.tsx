import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  SectionKey,
  isOwner,
  hasAnyPermission,
  defaultRoutePermissions,
  getRoleLabel,
} from '../utils/permissions';

interface ProtectedSectionProps {
  children: React.ReactNode;
  sectionKey: SectionKey;
  /** Если задано, достаточно любого из перечисленных прав (владелец — всегда ок). */
  requireAnyOf?: string[];
}

const ProtectedSection: React.FC<ProtectedSectionProps> = ({
  children,
  sectionKey,
  requireAnyOf,
}) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div style={{ padding: '20px', textAlign: 'center' }}>Загрузка...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="login" state={{ from: location }} replace />;
  }

  if (sectionKey === 'admins' || sectionKey === 'admin_roles') {
    if (!isOwner()) {
      return (
        <div style={{ padding: '40px', textAlign: 'center' }}>
          <h2>Доступ запрещен</h2>
          <p>Раздел доступен только владельцу.</p>
          <p style={{ color: '#888', marginTop: '1rem' }}>
            Вы: <strong>{getRoleLabel()}</strong>
          </p>
          <button
            type="button"
            onClick={() => window.history.back()}
            style={{ marginTop: '1rem', padding: '0.5rem 1rem', cursor: 'pointer' }}
          >
            Назад
          </button>
        </div>
      );
    }
  } else {
    const keys = requireAnyOf?.length ? requireAnyOf : defaultRoutePermissions(sectionKey);
    if (keys.length && !hasAnyPermission(keys)) {
      return (
        <div style={{ padding: '40px', textAlign: 'center' }}>
          <h2>Доступ запрещен</h2>
          <p>У вас нет прав для доступа к этому разделу.</p>
          <p style={{ color: '#888', marginTop: '1rem' }}>
            Вы: <strong>{getRoleLabel()}</strong>
          </p>
          <button
            type="button"
            onClick={() => window.history.back()}
            style={{ marginTop: '1rem', padding: '0.5rem 1rem', cursor: 'pointer' }}
          >
            Назад
          </button>
        </div>
      );
    }
  }

  return <>{children}</>;
};

export default ProtectedSection;
