import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { useAuth } from '../../contexts/AuthContext';
import { getUserDeliveryPresets, getDeliveryMethods, setDefaultUserDeliveryPreset } from '../../api/delivery';
import { track } from '../../utils/productAnalytics';
import './AddressesPage.css';

function hasProfilePhone(user) {
  const local = (user?.phone_local ?? '').toString().trim();
  return local.length > 0;
}

function SVGRadioSelected({ id }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g clipPath={`url(#clip_sel_addr_${id})`}>
        <circle cx="7" cy="7" r="4.5" stroke="#171717" strokeWidth="5" />
      </g>
      <defs>
        <clipPath id={`clip_sel_addr_${id}`}>
          <rect width="14" height="14" fill="white" />
        </clipPath>
      </defs>
    </svg>
  );
}

function SVGRadioUnselected({ id }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g clipPath={`url(#clip_un_addr_${id})`}>
        <circle cx="7" cy="7" r="6.5" stroke="#171717" />
      </g>
      <defs>
        <clipPath id={`clip_un_addr_${id}`}>
          <rect width="14" height="14" fill="white" />
        </clipPath>
      </defs>
    </svg>
  );
}

const SVG_EDIT_ARROW = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M6 4L11 7.5L6 11.5" stroke="#171717" />
  </svg>
);

export default function AddressesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTabBarVisible } = useTabBarVisibility();
  const { user } = useAuth();
  const fromCheckout = location.state?.fromCheckout === true;
  const selectedCartItemIds = location.state?.selectedCartItemIds ?? null;
  const [presets, setPresets] = useState([]);
  const [methods, setMethods] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [settingDefault, setSettingDefault] = useState(false);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) {
      return () => {
        setTabBarVisible(true);
      };
    }
    const handleBack = () => {
      navigate(-1);
    };
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
      setTabBarVisible(true);
    };
  }, [navigate, setTabBarVisible]);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [presetsData, methodsData] = await Promise.all([
          getUserDeliveryPresets(),
          getDeliveryMethods().catch(() => []),
        ]);
        const list = Array.isArray(presetsData) ? presetsData : [];
        setPresets(list);
        setMethods(Array.isArray(methodsData) ? methodsData : []);
        if (list.length) {
          const defaultPreset = list.find((p) => p.is_default);
          setSelectedId(defaultPreset ? defaultPreset.id : list[0].id);
        }
      } catch (e) {
        setError(e.message || 'Не удалось загрузить адреса');
        setPresets([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    track('addresses_view', { from_checkout: fromCheckout });
  }, [fromCheckout]);

  const handleSelect = async (preset) => {
    const id = preset.id;
    if (settingDefault) return;

    const alreadySelected = selectedId === id;

    // С экрана оформления заказа: клик по любому адресу (в т.ч. уже выбранному) возвращает в чекаут
    if (fromCheckout) {
      setSelectedId(id);
      track('addresses_pick_for_checkout', {
        preset_id: id,
        delivery_method_id: preset?.delivery_method_id ?? null,
      });
      navigate('/main/checkout', {
        state: { selectedCartItemIds, selectedDeliveryPreset: preset },
      });
      if (alreadySelected) return;
    } else if (alreadySelected) {
      return;
    }

    const previousId = selectedId;
    setSelectedId(id);
    try {
      setSettingDefault(true);
      setError(null);
      await setDefaultUserDeliveryPreset(id);
      setPresets((prev) =>
        prev.map((p) => ({ ...p, is_default: p.id === id }))
      );
    } catch (e) {
      setSelectedId(previousId);
      setError(e.message || 'Не удалось установить основной адрес');
    } finally {
      setSettingDefault(false);
    }
  };

  return (
    <div className="addresses-page page-container">
      <div className="addresses-page__header">
        <div className="addresses-page__header-text">Адреса доставки</div>
      </div>
      {loading && <p className="addresses-page__status">Загрузка…</p>}
      {error && !loading && (
        <p className="addresses-page__status addresses-page__status--error" role="alert">
          {error}
        </p>
      )}
      {!loading && !error && (
        <>
          {presets.length > 0 && (
            <div className="addresses-page__list">
              {presets.map((preset) => {
                const isSelected = selectedId === preset.id;
                const address = preset.address || 'Адрес не указан';
                const fio = preset.recipient_name || '';
                const phone = preset.phone_number || '';
                const method = methods.find((m) => m.id === preset.delivery_method_id);
                const typeLabel = method ? method.name : 'Доставка';
                return (
                  <article
                    key={preset.id}
                    className="address-card"
                    onClick={() => handleSelect(preset)}
                  >
                    <div className="address-card__row">
                      <button
                        type="button"
                        className="address-card__radio"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelect(preset);
                        }}
                        aria-checked={isSelected}
                        aria-label={isSelected ? 'Снять выбор адреса' : 'Выбрать адрес'}
                      >
                        {isSelected ? (
                          <SVGRadioSelected id={preset.id} />
                        ) : (
                          <SVGRadioUnselected id={preset.id} />
                        )}
                      </button>
                      <div className="address-card__content">
                        <div className="address-card__type">{typeLabel}</div>
                        <div className="address-card__address">{address}</div>
                        {(fio || phone) && (
                          <div className="address-card__meta">
                            {fio && <div className="address-card__meta-line">{fio}</div>}
                            {phone && <div className="address-card__meta-line">{phone}</div>}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        className="address-card__edit"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate('/main/profile/addresses/edit', { state: { preset } });
                        }}
                        aria-label="Редактировать адрес"
                      >
                        {SVG_EDIT_ARROW}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          <button
            type="button"
            className="addresses-page__add-btn"
            onClick={() => {
              if (!hasProfilePhone(user)) {
                const msg = 'Добавьте номер телефона в профиль, чтобы мы могли с вами связаться. Укажите номер в разделе «Профиль».';
                if (window.Telegram?.WebApp?.showAlert) {
                  window.Telegram.WebApp.showAlert(msg);
                } else {
                  alert(msg);
                }
                return;
              }
              navigate('/main/profile/addresses/edit');
            }}
          >
            <span className="addresses-page__add-btn-icon">
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <path
                  d="M12.25 7C12.25 7.11603 12.2039 7.22731 12.1219 7.30936C12.0398 7.39141 11.9285 7.4375 11.8125 7.4375H7.4375V11.8125C7.4375 11.9285 7.39141 12.0398 7.30936 12.1219C7.22731 12.2039 7.11603 12.25 7 12.25C6.88397 12.25 6.77269 12.2039 6.69064 12.1219C6.60859 12.0398 6.5625 11.9285 6.5625 11.8125V7.4375H2.1875C2.07147 7.4375 1.96019 7.39141 1.87814 7.30936C1.79609 7.22731 1.75 7.11603 1.75 7C1.75 6.88397 1.79609 6.77269 1.87814 6.69064C1.96019 6.60859 2.07147 6.5625 2.1875 6.5625H6.5625V2.1875C6.5625 2.07147 6.60859 1.96019 6.69064 1.87814C6.77269 1.79609 6.88397 1.75 7 1.75C7.11603 1.75 7.22731 1.79609 7.30936 1.87814C7.39141 1.96019 7.4375 2.07147 7.4375 2.1875V6.5625H11.8125C11.9285 6.5625 12.0398 6.60859 12.1219 6.69064C12.2039 6.77269 12.25 6.88397 12.25 7Z"
                  fill="#525252"
                />
              </svg>
            </span>
            <span className="addresses-page__add-btn-text">Добавить адрес</span>
          </button>
        </>
      )}
    </div>
  );
}

