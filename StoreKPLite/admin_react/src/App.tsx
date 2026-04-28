import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import Login from './pages/Login/Login';
import Layout from './components/Layout/Layout';
import ProtectedSection from './components/ProtectedSection';
import Users from './pages/Users/Users';
import UserDetail from './pages/Users/UserDetail';
import Admins from './pages/Admins/Admins';
import AdminDetail from './pages/Admins/AdminDetail';
import AdminRoles from './pages/AdminRoles/AdminRoles';
import Catalog from './pages/Catalog/Catalog';
import ItemDetail from './pages/Catalog/ItemDetail';
import ItemForm from './pages/Catalog/ItemForm';
import ItemGroups from './pages/Catalog/ItemGroups';
import ItemGroupDetail from './pages/Catalog/ItemGroupDetail';
import ItemTypes from './pages/Catalog/ItemTypes';
import BulkItemForm from './pages/Catalog/BulkItemForm';
import Orders from './pages/Orders/Orders';
import ManualOrderForm from './pages/Orders/ManualOrderForm';
import './App.css';

const ADMIN_BASE = process.env.PUBLIC_URL || '/admin';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return <div style={{ padding: '20px', textAlign: 'center' }}>Загрузка...</div>;
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="login" replace />;
};

function App() {
  return (
    <AuthProvider>
      <Router basename={ADMIN_BASE}>
        <Routes>
          <Route path="login" element={<Login />} />
          <Route
            path=""
            element={
              <ProtectedRoute>
                <ErrorBoundary>
                  <Layout />
                </ErrorBoundary>
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="orders" replace />} />
            <Route path="dashboard" element={<Navigate to="orders" replace />} />
            <Route path="users" element={<ProtectedSection sectionKey="users"><Users /></ProtectedSection>} />
            <Route path="users/:userId" element={<ProtectedSection sectionKey="users"><UserDetail /></ProtectedSection>} />
            <Route path="admins" element={<ProtectedSection sectionKey="admins"><Admins /></ProtectedSection>} />
            <Route path="admins/:userId" element={<ProtectedSection sectionKey="admins"><AdminDetail /></ProtectedSection>} />
            <Route path="admin-roles" element={<ProtectedSection sectionKey="admin_roles"><AdminRoles /></ProtectedSection>} />
            <Route path="catalog" element={<ProtectedSection sectionKey="catalog"><Catalog /></ProtectedSection>} />
            <Route path="catalog/groups" element={<ProtectedSection sectionKey="catalog"><ItemGroups /></ProtectedSection>} />
            <Route path="catalog/groups/:groupId" element={<ProtectedSection sectionKey="catalog"><ItemGroupDetail /></ProtectedSection>} />
            <Route path="catalog/types" element={<ProtectedSection sectionKey="catalog"><ItemTypes /></ProtectedSection>} />
            <Route path="catalog/new" element={<ProtectedSection sectionKey="catalog"><ItemForm /></ProtectedSection>} />
            <Route path="catalog/bulk-create" element={<ProtectedSection sectionKey="catalog"><BulkItemForm /></ProtectedSection>} />
            <Route path="catalog/:itemId" element={<ProtectedSection sectionKey="catalog"><ItemDetail /></ProtectedSection>} />
            <Route path="catalog/:itemId/edit" element={<ProtectedSection sectionKey="catalog"><ItemForm /></ProtectedSection>} />
            <Route path="orders" element={<ProtectedSection sectionKey="orders"><Orders /></ProtectedSection>} />
            <Route path="orders/manual" element={<ProtectedSection sectionKey="orders"><ManualOrderForm /></ProtectedSection>} />
            <Route path="*" element={<Navigate to="orders" replace />} />
          </Route>
          <Route path="/" element={<Navigate to="login" replace />} />
          <Route path="*" element={<Navigate to="login" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
