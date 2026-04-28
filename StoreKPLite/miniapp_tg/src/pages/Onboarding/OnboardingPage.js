import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { useAuth } from '../../contexts/AuthContext';
import Button from '../../components/Button';
import { track } from '../../utils/productAnalytics';
import './OnboardingPage.css';

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { setTabBarVisible } = useTabBarVisibility();
  const { user, acceptPolicy, loading, error } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const logoUrl = process.env.PUBLIC_URL + '/static/mainstatic/logo.svg';

  useEffect(() => {
    setTabBarVisible(false);
    return () => setTabBarVisible(true);
  }, [setTabBarVisible]);

  const handleGoToPurchases = async () => {
    if (submitting) return;
    setSubmitting(true);
    const ok = await acceptPolicy();
    setSubmitting(false);
    if (ok) {
      track('onboarding_policy_accept', {});
      navigate('/main/catalog', { replace: true });
    }
  };

  return (
    <div className="onboarding-page">
      <header className="onboarding-page__header" aria-hidden="false">
        <img src={logoUrl} alt="MatchWear" className="onboarding-page__logo" />
      </header>
      <div className="onboarding-page__body">
        <div className="onboarding-page__content">
          {loading && !user ? (
            <p className="onboarding-page__loading">Загрузка…</p>
          ) : error ? (
            <p className="onboarding-page__error">{error}</p>
          ) : (
            <>
              <div className="onboarding-page__card">
                <div className="onboarding-page__card-inner">
                  <img
                    src={process.env.PUBLIC_URL + '/static/mainstatic/matchwear.jpg'}
                    alt=""
                    className="onboarding-page__bg"
                  />
                </div>
              </div>
              <Button
                size="large"
                variant="primary"
                onClick={handleGoToPurchases}
                loading={submitting}
              >
                К покупкам
              </Button>
              <p className="onboarding-page__policy">
                Нажимая кнопку “К покупкам” вы соглашаетесь
                <br />
                с{' '}
                <Link to="/policy">политикой конфиденциальности</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
