import React, { useRef, useState } from 'react';
import './MainAppContainer.css';
import TabBar from '../components/TabBar';
import { useTabBarVisibility } from '../contexts/TabBarVisibilityContext';

const logoUrl = process.env.PUBLIC_URL + '/static/mainstatic/logo.svg';

const MainAppContainer = ({ webApp }) => {
  const mainContentRef = useRef(null);
  const [activeTab, setActiveTab] = useState('feed');
  const { tabBarVisible } = useTabBarVisibility();

  const containerClass = `main-app-container${tabBarVisible ? ' main-app-container--tabbar-visible' : ''}`;

  return (
    <div className={containerClass}>
      <header className="main-app-header" aria-hidden="false">
        <img src={logoUrl} alt="MatchWear" className="main-app-logo" />
      </header>
      <div className="main-app-content" ref={mainContentRef}>
        <div className="page-container page-container--placeholder">
          <p className="placeholder-text">MatchWear</p>
          <p className="placeholder-sub">Mini app is running. Catalog and orders coming soon.</p>
        </div>
      </div>
      {tabBarVisible && (
        <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
      )}
    </div>
  );
};

export default MainAppContainer;
