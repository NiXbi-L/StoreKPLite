import React, { useState, useEffect } from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getAvailableSections, getRoleLabel } from '../../utils/permissions';
import './Layout.css';

const Layout: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const availableSections = getAvailableSections();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const closeSidebar = () => {
    setSidebarOpen(false);
  };

  // Закрываем sidebar при клике вне его на мобильных
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 768) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="layout">
      <button className="menu-toggle" onClick={toggleSidebar} aria-label="Toggle menu">
        <span></span>
        <span></span>
        <span></span>
      </button>
      {sidebarOpen && <div className="sidebar-overlay" onClick={closeSidebar}></div>}
      <nav className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="sidebar-header">
          <h2>MatchWear</h2>
          <p>Admin Panel</p>
          <p style={{ fontSize: '0.85rem', color: '#888', marginTop: '0.25rem' }}>
            {getRoleLabel()}
          </p>
          <button className="sidebar-close" onClick={closeSidebar} aria-label="Close menu">×</button>
        </div>
        <ul className="sidebar-menu">
          {availableSections.map((section) => (
            <li key={section.key}>
              <Link to={section.path} onClick={closeSidebar}>
                {section.icon} {section.name}
              </Link>
            </li>
          ))}
        </ul>
        <div className="sidebar-footer">
          <button onClick={handleLogout} className="logout-btn">Выйти</button>
        </div>
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;

