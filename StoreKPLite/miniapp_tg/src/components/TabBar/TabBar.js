import React from 'react';
import './TabBar.css';
import { IconCart, IconCatalog, IconProfile } from './TabBarIcons';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';

const TABS = [
  { id: 'catalog', label: 'Каталог', Icon: IconCatalog },
  { id: 'cart', label: 'Корзина', Icon: IconCart },
  { id: 'profile', label: 'Профиль', Icon: IconProfile },
];

export default function TabBar({ activeTab, onTabChange }) {
  const { tabBarVisible } = useTabBarVisibility();

  return (
    <nav
      className={`tabbar ${tabBarVisible ? '' : 'tabbar--hidden'}`}
      role="tablist"
      aria-label="Навигация"
    >
      {TABS.map((tab) => {
        const Icon = tab.Icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={tab.label}
            className={`tabbar__btn ${isActive ? 'tabbar__btn--active' : ''}`}
            onClick={() => onTabChange && onTabChange(tab.id)}
          >
            <Icon className="tabbar__icon" />
            <span className="tabbar__label">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
