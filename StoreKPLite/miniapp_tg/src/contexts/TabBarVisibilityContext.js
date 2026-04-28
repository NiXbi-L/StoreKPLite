import React, { createContext, useContext, useState } from 'react';

const TabBarVisibilityContext = createContext(null);

export function TabBarVisibilityProvider({ children }) {
  const [tabBarVisible, setTabBarVisible] = useState(true);
  return (
    <TabBarVisibilityContext.Provider value={{ tabBarVisible, setTabBarVisible }}>
      {children}
    </TabBarVisibilityContext.Provider>
  );
}

export function useTabBarVisibility() {
  const ctx = useContext(TabBarVisibilityContext);
  if (!ctx) {
    return {
      tabBarVisible: true,
      setTabBarVisible: () => {},
    };
  }
  return ctx;
}
