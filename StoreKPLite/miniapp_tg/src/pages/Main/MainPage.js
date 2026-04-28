import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import './MainPage.css';
import TabBar from '../../components/TabBar';
import BrowserNavBackButton from '../../components/BrowserNavBackButton/BrowserNavBackButton';
import BrowserCatalogShareButton from '../../components/BrowserCatalogShareButton/BrowserCatalogShareButton';
import { CatalogShareDispatchContext } from '../../contexts/CatalogShareContext';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { CatalogProvider } from '../../contexts/CatalogContext';
import { isTelegramWebAppEnvironment } from '../../utils/telegramEnvironment';
import { BrowserBackHandlerRefProvider, useBrowserBackHandlerRef } from '../../contexts/BrowserBackHandlerRefContext';
import { track } from '../../utils/productAnalytics';

const logoUrl = process.env.PUBLIC_URL + '/static/mainstatic/logo.svg';

const ROOT_TAB_SEGMENTS = ['cart', 'catalog', 'profile'];

function routePathForBrowserUi(loc) {
  let p = (loc.pathname || '').trim();
  if (p && p !== '/' && p.includes('main')) {
    return p.replace(/\/+$/, '') || '/';
  }
  const h = loc.hash || '';
  if (h.startsWith('#')) {
    return (h.slice(1).split('?')[0] || '/').replace(/\/+$/, '') || '/';
  }
  return p || '/';
}

function hasInAppProductNavigationState(state) {
  if (!state || typeof state !== 'object') return false;
  return Boolean(
    state.item ||
      state.fromRelated ||
      state.fromFeed ||
      state.fromOrders ||
      state.fromStartappItem
  );
}

function MainPageInner() {
  const browserBackHandlerRef = useBrowserBackHandlerRef();
  const mainContentRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('catalog');
  const { setTabBarVisible } = useTabBarVisibility();

  useEffect(() => {
    const threshold = 80;
    const baseHeight = window.innerHeight;

    const handleResize = () => {
      const path = window.location.hash.replace('#', '') || '';
      const segments = path.split('/').filter(Boolean);
      const isRootTabPage =
        segments[0] === 'main' &&
        (segments.length === 1 || (segments.length === 2 && ROOT_TAB_SEGMENTS.includes(segments[1])));

      if (!isRootTabPage) {
        setTabBarVisible(false);
        return;
      }
      const currentHeight = window.innerHeight;
      const keyboardOpen = baseHeight - currentHeight > threshold;
      setTabBarVisible(!keyboardOpen);
    };

    window.addEventListener('resize', handleResize);

    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', handleResize);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener('resize', handleResize);
      }
    };
  }, [setTabBarVisible]);

  const browserUiPath = useMemo(
    () => routePathForBrowserUi(location),
    [location.pathname, location.hash]
  );

  const isRootTabPage = useMemo(() => {
    const segments = browserUiPath.split('/').filter(Boolean);
    return (
      segments[0] === 'main' &&
      (segments.length === 1 || (segments.length === 2 && ROOT_TAB_SEGMENTS.includes(segments[1])))
    );
  }, [browserUiPath]);

  const isBrowserCatalogItemOrphan = useMemo(() => {
    if (isTelegramWebAppEnvironment()) return false;
    const segments = browserUiPath.split('/').filter(Boolean);
    const isLeafItem =
      segments.length === 3 &&
      segments[0] === 'main' &&
      segments[1] === 'catalog' &&
      /^\d+$/.test(segments[2]);
    return isLeafItem && !hasInAppProductNavigationState(location.state);
  }, [browserUiPath, location.state]);

  useEffect(() => {
    const tabSegment = browserUiPath.split('/').filter(Boolean)[1] || '';
    const rootTab = ROOT_TAB_SEGMENTS.includes(tabSegment) ? tabSegment : null;
    track('screen_view', { path: browserUiPath, root_tab: rootTab });
  }, [browserUiPath]);

  useEffect(() => {
    const segments = browserUiPath.split('/').filter(Boolean);
    const tabSegment = segments[1];

    switch (tabSegment) {
      case 'cart':
        setActiveTab('cart');
        break;
      case 'catalog':
        setActiveTab('catalog');
        break;
      case 'profile':
        setActiveTab('profile');
        break;
      default:
        setActiveTab('catalog');
        break;
    }

    setTabBarVisible(isRootTabPage);
  }, [browserUiPath, setTabBarVisible, isRootTabPage]);

  const showBrowserHeaderBack = !isTelegramWebAppEnvironment() && !isRootTabPage;
  const [catalogSharePayload, setCatalogSharePayload] = useState(null);

  const handleBrowserBack = useCallback(() => {
    const override = browserBackHandlerRef.current;
    if (typeof override === 'function') {
      override();
      return;
    }
    if (isBrowserCatalogItemOrphan) {
      navigate('/main/catalog');
      return;
    }
    navigate(-1);
  }, [browserBackHandlerRef, navigate, isBrowserCatalogItemOrphan]);

  const handleTabChange = (tabId) => {
    let segment = 'catalog';
    if (tabId === 'cart') segment = 'cart';
    else if (tabId === 'catalog') segment = 'catalog';
    else if (tabId === 'profile') segment = 'profile';
    navigate(`/main/${segment}`, { replace: false });
  };

  const showBrowserCatalogShare =
    !isTelegramWebAppEnvironment() && catalogSharePayload != null;

  return (
    <div className="main-page">
      <header className="main-page__header" aria-hidden="false">
        <div className="main-page__header-leading">
          {showBrowserHeaderBack ? (
            <BrowserNavBackButton onClick={handleBrowserBack} />
          ) : (
            <span className="main-page__header-leading-spacer" aria-hidden />
          )}
        </div>
        <div className="main-page__header-center">
          <button
            type="button"
            className="main-page__logo-wrap"
            onClick={() => {
              navigate('/main/catalog');
            }}
            aria-label="В каталог"
          >
            <img src={logoUrl} alt="MatchWear" className="main-page__logo" />
          </button>
        </div>
        <div
          className="main-page__header-trailing"
          aria-hidden={!showBrowserCatalogShare}
        >
          {showBrowserCatalogShare ? (
            <BrowserCatalogShareButton
              itemId={catalogSharePayload.itemId}
              title={catalogSharePayload.title}
            />
          ) : (
            <span className="main-page__header-trailing-spacer" aria-hidden />
          )}
        </div>
      </header>
      <div className="main-page__content" ref={mainContentRef}>
        <CatalogProvider>
          <CatalogShareDispatchContext.Provider value={setCatalogSharePayload}>
            <Outlet />
          </CatalogShareDispatchContext.Provider>
        </CatalogProvider>
      </div>
      <TabBar activeTab={activeTab} onTabChange={handleTabChange} />
    </div>
  );
}

export default function MainPage() {
  return (
    <BrowserBackHandlerRefProvider>
      <MainPageInner />
    </BrowserBackHandlerRefProvider>
  );
}
