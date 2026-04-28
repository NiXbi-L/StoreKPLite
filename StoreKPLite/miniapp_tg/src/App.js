import React, { useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import './App.css';
import { resetDocumentThemeOverrides } from './themeReset';
import { TabBarVisibilityProvider } from './contexts/TabBarVisibilityContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import {
  OnboardingPage,
  MainPage,
  CartPage,
  CatalogPage,
  CatalogItemPage,
  ItemReviewsPage,
  ProfilePage,
  LikedPage,
  AddressesPage,
  AddressEditPage,
  CdekPickupStubPage,
  CheckoutPage,
  OrdersPage,
  LeaveReviewPage,
  PolicyPage,
  PublicOfferPage,
  BrowserLoginPage,
  BrowserLoginQrPage,
} from './pages';
import { markStartappItemRoot } from './utils/startappItemEntry';
import { isTelegramWebAppEnvironment, hasTelegramWebAppInitData } from './utils/telegramEnvironment';
import RequireWebUser from './components/RequireWebUser/RequireWebUser';
import { initProductAnalytics, shutdownProductAnalytics } from './utils/productAnalytics';

function _readTgStartParamFromLocation() {
  const hash = window.location.hash.slice(1);
  const qIdx = hash.indexOf('?');
  const queryFromHash = qIdx >= 0 ? hash.slice(qIdx + 1) : '';
  const params = new URLSearchParams(queryFromHash);
  let startParam = params.get('tgWebAppStartParam') || '';
  if (!startParam && typeof window.location.search === 'string' && window.location.search.length > 1) {
    const p2 = new URLSearchParams(window.location.search.slice(1));
    startParam = p2.get('tgWebAppStartParam') || '';
  }
  if (!startParam && isTelegramWebAppEnvironment()) {
    startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param || '';
  }
  return startParam;
}

function useStartParamRedirect() {
  const navigate = useNavigate();
  const didRedirectRef = React.useRef(false);
  useEffect(() => {
    if (didRedirectRef.current) return;
    const tryRedirect = () => {
      if (didRedirectRef.current) return false;
      const startParam = _readTgStartParamFromLocation();
      const m = /^item_(\d+)$/.exec(startParam);
      if (m) {
        didRedirectRef.current = true;
        const itemId = m[1];
        markStartappItemRoot(itemId);
        navigate(`/main/catalog/${itemId}`, { replace: true, state: { fromStartappItem: true } });
        return true;
      }
      return false;
    };
    if (tryRedirect()) return undefined;
    let n = 0;
    const id = setInterval(() => {
      n += 1;
      if (tryRedirect() || n >= 25) {
        clearInterval(id);
      }
    }, 120);
    return () => clearInterval(id);
  }, [navigate]);
}

function RootRedirect() {
  const { user, isPolicyAccepted } = useAuth();
  if (!user && !hasTelegramWebAppInitData()) {
    return <Navigate to="/main/catalog" replace />;
  }
  if (user && !isPolicyAccepted) {
    return <Navigate to="/onboarding" replace />;
  }
  return <Navigate to="/main/catalog" replace />;
}

function AppRoutes() {
  const { user, loading, isPolicyAccepted } = useAuth();

  useStartParamRedirect();

  useEffect(() => {
    resetDocumentThemeOverrides();
    if (!isTelegramWebAppEnvironment()) return undefined;
    const tg = window.Telegram?.WebApp;
    if (!tg) return undefined;
    tg.ready();
    tg.expand();
    const isMobile = /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|webOS/i.test(navigator.userAgent);
    if (isMobile) {
      tg.requestFullscreen?.();
      tg.disableVerticalSwipes?.();
      tg.lockOrientation?.();
    }
    document.documentElement.style.setProperty('--ios-safe-area-inset-top', '0px');
    return undefined;
  }, []);

  if (loading && !user) {
    return (
      <div className="app app--loading">
        <p>Загрузка…</p>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/browser-login/qr"
        element={user ? <Navigate to="/" replace /> : <BrowserLoginQrPage />}
      />
      <Route
        path="/browser-login"
        element={user ? <Navigate to="/" replace /> : <BrowserLoginPage />}
      />
      <Route path="/" element={<RootRedirect />} />
      <Route
        path="/onboarding"
        element={
          user && !isPolicyAccepted ? (
            <OnboardingPage />
          ) : user && isPolicyAccepted ? (
            <Navigate to="/main/catalog" replace />
          ) : !hasTelegramWebAppInitData() ? (
            <Navigate to="/main/catalog" replace />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route path="/policy" element={<PolicyPage />} />
      <Route path="/public-offer" element={<PublicOfferPage />} />
      <Route path="/main" element={<MainPage />}>
        <Route index element={<Navigate to="/main/catalog" replace />} />
        <Route
          path="cart"
          element={
            <RequireWebUser>
              <CartPage />
            </RequireWebUser>
          }
        />
        <Route
          path="checkout"
          element={
            <RequireWebUser>
              <CheckoutPage />
            </RequireWebUser>
          }
        />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="catalog/:itemId" element={<CatalogItemPage />} />
        <Route path="catalog/:itemId/reviews" element={<ItemReviewsPage />} />
        <Route
          path="profile"
          element={
            <RequireWebUser>
              <ProfilePage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/liked"
          element={
            <RequireWebUser>
              <LikedPage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/addresses"
          element={
            <RequireWebUser>
              <AddressesPage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/addresses/edit"
          element={
            <RequireWebUser>
              <AddressEditPage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/addresses/cdek-pvz"
          element={
            <RequireWebUser>
              <CdekPickupStubPage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/orders"
          element={
            <RequireWebUser>
              <OrdersPage />
            </RequireWebUser>
          }
        />
        <Route
          path="profile/orders/:orderId/review"
          element={
            <RequireWebUser>
              <LeaveReviewPage />
            </RequireWebUser>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function ProductAnalyticsBoot() {
  useEffect(() => {
    initProductAnalytics();
    return () => shutdownProductAnalytics();
  }, []);
  return null;
}

function MiniappShell() {
  const { guestHtml } = useAuth();
  if (guestHtml != null) {
    return (
      <iframe
        title="Сообщение"
        srcDoc={guestHtml}
        style={{ border: 0, width: '100%', minHeight: '100vh', display: 'block' }}
      />
    );
  }
  return (
    <>
      <ProductAnalyticsBoot />
      <AppRoutes />
    </>
  );
}

function App() {
  return (
    <HashRouter>
      <AuthProvider>
        <TabBarVisibilityProvider>
          <div className="app-viewport">
            <div className="app">
              <MiniappShell />
            </div>
          </div>
        </TabBarVisibilityProvider>
      </AuthProvider>
    </HashRouter>
  );
}

export default App;
