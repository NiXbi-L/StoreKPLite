import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { useAuth } from '../../contexts/AuthContext';
import {
  getDeliveryMethods,
  getLocalPickupPoints,
  getUserDeliveryPresets,
  saveUserDeliveryPreset,
  updateUserDeliveryPreset,
  deleteUserDeliveryPreset,
} from '../../api/delivery';
import Button from '../../components/Button';
import './AddressEditPage.css';

/** Полный номер из профиля: country_code + phone_local (как в ProfilePage) */
function getProfilePhoneFull(user) {
  const cc = (user?.country_code ?? '').toString().trim();
  const local = (user?.phone_local ?? '').toString().trim();
  if (!local) return '';
  return cc ? `${cc} ${local}`.trim() : local;
}

function hasProfilePhone(user) {
  return getProfilePhoneFull(user).length > 0;
}

const SVG_ARROW_RIGHT = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M6 4L11 7.5L6 11.5" stroke="#171717" />
  </svg>
);

const ADDRESS_EDIT_STORAGE_KEY = 'addressEditFormState';

function getRestoredState(location) {
  const editState = location?.state?.editState ?? null;
  if (editState) {
    return {
      selectedCode: editState.selectedCode ?? 'PICKUP_LOCAL',
      recipientName: editState.recipientName ?? '',
      phone: editState.phone ?? '',
      address: editState.address ?? '',
      pickupPointCode: editState.pickupPointCode ?? '',
      pickupPointLabel: editState.pickupPointLabel ?? '',
      cdekPostalCode: editState.cdekPostalCode ?? '',
      cdekCityCode: editState.cdekCityCode ?? '',
      selectedLocalPickupId: editState.selectedLocalPickupId ?? null,
    };
  }
  try {
    const raw = sessionStorage.getItem(ADDRESS_EDIT_STORAGE_KEY);
    if (raw) {
      sessionStorage.removeItem(ADDRESS_EDIT_STORAGE_KEY);
      const data = JSON.parse(raw);
      return {
        selectedCode: data.selectedCode ?? 'PICKUP_LOCAL',
        recipientName: data.recipientName ?? '',
        phone: data.phone ?? '',
        address: data.address ?? '',
        pickupPointCode: data.pickupPointCode ?? '',
        pickupPointLabel: data.pickupPointLabel ?? '',
        cdekPostalCode: data.cdekPostalCode ?? '',
        cdekCityCode: data.cdekCityCode ?? '',
        selectedLocalPickupId: data.selectedLocalPickupId ?? null,
      };
    }
  } catch (_) {}
  return null;
}

export default function AddressEditPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTabBarVisible } = useTabBarVisibility();
  const { user } = useAuth();

  const initialRestored = getRestoredState(location);
  const noProfilePhone = !hasProfilePhone(user);
  const [methods, setMethods] = useState([]);
  const [selectedCode, setSelectedCode] = useState(initialRestored?.selectedCode ?? 'PICKUP_LOCAL');
  const [recipientName, setRecipientName] = useState(initialRestored?.recipientName ?? '');
  const [phone, setPhone] = useState(initialRestored?.phone ?? getProfilePhoneFull(user) ?? '');
  const [address, setAddress] = useState(initialRestored?.address ?? '');
  const [pickupPointCode, setPickupPointCode] = useState(initialRestored?.pickupPointCode ?? '');
  const [pickupPointLabel, setPickupPointLabel] = useState(initialRestored?.pickupPointLabel ?? '');
  const [cdekPostalCode, setCdekPostalCode] = useState(initialRestored?.cdekPostalCode ?? '');
  const [cdekCityCode, setCdekCityCode] = useState(initialRestored?.cdekCityCode ?? '');
  const [loadingMethods, setLoadingMethods] = useState(!initialRestored);
  const [error, setError] = useState(null);
  const [localPickupPoints, setLocalPickupPoints] = useState([]);
  const [selectedLocalPickupId, setSelectedLocalPickupId] = useState(initialRestored?.selectedLocalPickupId ?? null);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const editPreset = location.state?.preset ?? null;
  const isEditMode = Boolean(editPreset);

  useEffect(() => {
    // На этой странице таббар всегда скрыт
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

  // При возврате с карты подтягиваем форму из state или sessionStorage (state при go(-1) может не приходить)
  useEffect(() => {
    const editState = location.state?.editState ?? null;
    const selectedPickupPoint = location.state?.selectedPickupPoint ?? null;

    if (editState) {
      setSelectedCode(editState.selectedCode ?? 'PICKUP_LOCAL');
      setRecipientName(editState.recipientName ?? '');
      setPhone(editState.phone ?? '');
      setAddress(editState.address ?? '');
      setPickupPointCode(editState.pickupPointCode ?? '');
      setPickupPointLabel(editState.pickupPointLabel ?? '');
      setCdekPostalCode(editState.cdekPostalCode ?? '');
      setCdekCityCode(editState.cdekCityCode ?? '');
      setSelectedLocalPickupId(editState.selectedLocalPickupId ?? null);
    }
    if (selectedPickupPoint) {
      setPickupPointCode(selectedPickupPoint.code ?? '');
      setPickupPointLabel(selectedPickupPoint.label ?? selectedPickupPoint.address ?? '');
      setCdekPostalCode(
        selectedPickupPoint.postal_code != null ? String(selectedPickupPoint.postal_code).trim() : ''
      );
      setCdekCityCode(
        selectedPickupPoint.city_code != null && String(selectedPickupPoint.city_code).trim() !== ''
          ? String(selectedPickupPoint.city_code)
          : ''
      );
    }

    if (editState || selectedPickupPoint) {
      setLoadingMethods(false);
      return;
    }

    try {
      const raw = sessionStorage.getItem(ADDRESS_EDIT_STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      sessionStorage.removeItem(ADDRESS_EDIT_STORAGE_KEY);
      setSelectedCode(data.selectedCode ?? 'PICKUP_LOCAL');
      setRecipientName(data.recipientName ?? '');
      setPhone(data.phone ?? '');
      setAddress(data.address ?? '');
      setPickupPointCode(data.pickupPointCode ?? '');
      setPickupPointLabel(data.pickupPointLabel ?? '');
      setCdekPostalCode(data.cdekPostalCode ?? '');
      setCdekCityCode(data.cdekCityCode ?? '');
      setSelectedLocalPickupId(data.selectedLocalPickupId ?? null);
      setLoadingMethods(false);
    } catch (_) {}
  }, [location.state, location.key]);

  // Подставить номер из профиля (country_code + phone_local), если поле телефона пустое (user может подгрузиться после первого рендера)
  useEffect(() => {
    if (!user || !hasProfilePhone(user)) return;
    const profilePhone = getProfilePhoneFull(user);
    if (!profilePhone) return;
    setPhone((prev) => {
      const cur = (prev ?? '').toString().trim();
      return cur ? prev : profilePhone;
    });
  }, [user]);

  // Локальный детектор клавиатуры, чтобы прятать нижнюю кнопку
  useEffect(() => {
    const threshold = 80;
    const baseHeight = window.innerHeight;

    const handleResize = () => {
      const currentHeight = window.innerHeight;
      const isOpen = baseHeight - currentHeight > threshold;
      setKeyboardOpen(isOpen);
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
  }, []);

  // Загрузка способов доставки и ПВЗ; при возврате с карты форма уже восстановлена (initialRestored / editState), подгружаем только списки в фоне
  useEffect(() => {
    let cancelled = false;
    const editState = location.state?.editState ?? null;
    const hasRestored = initialRestored != null || editState != null;

    if (!hasRestored) {
      setLoadingMethods(true);
    }
    setError(null);

    async function load() {
      try {
        const [methodsData, pickupData, presetsData] = await Promise.all([
          getDeliveryMethods(),
          getLocalPickupPoints().catch(() => []),
          getUserDeliveryPresets().catch(() => []),
        ]);
        if (cancelled) return;
        const list = Array.isArray(methodsData) ? methodsData : [];
        setMethods(list);
        const pickupList = Array.isArray(pickupData) ? pickupData : [];
        setLocalPickupPoints(pickupList);

        if (hasRestored) {
          return;
        }

        const presets = Array.isArray(presetsData) ? presetsData : [];
        const preset = editPreset || presets[0] || null;

        if (list.length) {
          if (preset && preset.delivery_method_id != null) {
            const methodFromPreset = list.find((m) => m.id === preset.delivery_method_id);
            if (methodFromPreset) {
              setSelectedCode(methodFromPreset.code);
            } else {
              setSelectedCode(list[0].code);
            }
          } else {
            setSelectedCode(list[0].code);
          }
        }

        if (pickupList.length) {
          if (preset && preset.address) {
            const byAddress = pickupList.find((p) => p.address === preset.address);
            setSelectedLocalPickupId(byAddress ? byAddress.id : pickupList[0].id);
          } else {
            setSelectedLocalPickupId(pickupList[0].id);
          }
        }

        if (preset) {
          if (preset.recipient_name) setRecipientName(preset.recipient_name);
          if (preset.phone_number) setPhone(preset.phone_number);
          const methodForPreset = list.find((m) => m.id === preset.delivery_method_id);
          if (preset.address && methodForPreset?.code === 'COURIER_LOCAL') setAddress(preset.address);
          if (preset.address && methodForPreset?.code === 'CDEK_MANUAL') setAddress(preset.address);
          if (methodForPreset?.code === 'CDEK') {
            if (preset.address) setPickupPointLabel(preset.address);
            if (preset.cdek_delivery_point_code) {
              setPickupPointCode(String(preset.cdek_delivery_point_code).trim());
            }
            if (preset.postal_code) setCdekPostalCode(String(preset.postal_code).trim());
            if (preset.city_code != null && String(preset.city_code).trim() !== '') {
              setCdekCityCode(String(preset.city_code).trim());
            }
          }
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Не удалось загрузить способы доставки');
      } finally {
        if (!cancelled) setLoadingMethods(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [location.state?.editState]);

  const currentMethod = methods.find((m) => m.code === selectedCode) || null;
  const required = currentMethod?.required_fields || [];

  const isValid =
    !loadingMethods &&
    (!required.includes('recipient_name') || !!recipientName.trim()) &&
    (!required.includes('phone') || !!phone.trim()) &&
    (!required.includes('address') || !!address.trim()) &&
    (!required.includes('pickup_point_code') || !!pickupPointCode);

  const handleDelete = async () => {
    if (!isEditMode || deleting || !editPreset?.id) return;
    if (!window.confirm('Удалить этот адрес?')) return;
    try {
      setDeleting(true);
      await deleteUserDeliveryPreset(editPreset.id);
      navigate(-1);
    } catch (e) {
      setError(e.message || 'Не удалось удалить адрес');
    } finally {
      setDeleting(false);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isValid || saving) return;

    const method = methods.find((m) => m.code === selectedCode) || null;
    const methodRequired = method?.required_fields || [];

    let payloadAddress = null;

    if (selectedCode === 'PICKUP_LOCAL') {
      if (isEditMode) {
        payloadAddress = address || null;
      } else {
        const selectedPoint =
          localPickupPoints.find((point) => point.id === selectedLocalPickupId) || localPickupPoints[0] || null;
        payloadAddress = selectedPoint ? selectedPoint.address : null;
      }
    } else if (selectedCode === 'CDEK') {
      // Для CDEK сохраняем выбранный ПВЗ как текстовое описание
      payloadAddress = pickupPointLabel || null;
    } else if (methodRequired.includes('address')) {
      payloadAddress = address || null;
    }

    const payload = {
      phone_number: phone || null,
      recipient_name: recipientName || null,
      delivery_method_id: method ? method.id : null,
      address: payloadAddress,
    };

    if (selectedCode === 'CDEK') {
      const cc = parseInt(String(cdekCityCode).trim(), 10);
      payload.postal_code = cdekPostalCode.trim() || null;
      payload.city_code = Number.isFinite(cc) ? cc : null;
      payload.cdek_delivery_point_code = pickupPointCode.trim() || null;
    }

    try {
      setSaving(true);
      if (isEditMode && editPreset?.id) {
        await updateUserDeliveryPreset(editPreset.id, payload);
      } else {
        await saveUserDeliveryPreset(payload);
      }
      navigate(-1);
    } catch (e) {
      setError(e.message || 'Не удалось сохранить адрес');
    } finally {
      setSaving(false);
    }
  };

  if (noProfilePhone) {
    return (
      <div className="address-edit-page address-edit-page--blocked">
        <div className="address-edit-page__header">
          <div className="address-edit-page__header-text">
            {isEditMode ? 'Редактирование адреса' : 'Новый адрес'}
          </div>
        </div>
        <div className="address-edit-page__phone-required">
          <p className="address-edit-page__phone-required-text">
            Добавьте номер телефона в профиль, чтобы мы могли с вами связаться. Укажите номер в разделе «Профиль» в приложении.
          </p>
          <Button
            type="button"
            variant="primary"
            size="large"
            className="address-edit-page__phone-required-btn"
            onClick={() => navigate('/main/profile')}
          >
            Перейти в профиль
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="address-edit-page">
      <div className="address-edit-page__header">
        <div className="address-edit-page__header-text">
          {isEditMode ? 'Редактирование адреса' : 'Новый адрес'}
        </div>
      </div>

      {loadingMethods && <p className="addresses-page__status">Загрузка способов доставки…</p>}
      {error && !loadingMethods && (
        <p className="addresses-page__status addresses-page__status--error" role="alert">
          {error}
        </p>
      )}

      {!loadingMethods && !error && (
        <form className="address-edit-page__form" onSubmit={handleSubmit}>
          {!isEditMode && (
            <div className="address-edit-page__methods">
              {methods.map((method) => (
                <button
                  key={method.id}
                  type="button"
                  className={
                    'address-edit-page__method-btn' +
                    (selectedCode === method.code ? ' address-edit-page__method-btn--active' : '')
                  }
                  onClick={() => setSelectedCode(method.code)}
                >
                  {method.name}
                </button>
              ))}
            </div>
          )}

          {required.includes('recipient_name') && (
            <div className="address-edit-page__field">
              <label className="address-edit-page__label" htmlFor="recipientName">
                ФИО получателя
              </label>
              <input
                id="recipientName"
                className="address-edit-page__input"
                type="text"
                value={recipientName}
                onChange={(e) => setRecipientName(e.target.value)}
                placeholder="Введите ФИО"
              />
            </div>
          )}

          {required.includes('phone') && (
            <div className="address-edit-page__field">
              <label className="address-edit-page__label" htmlFor="phone">
                Телефон
              </label>
              <input
                id="phone"
                className="address-edit-page__input"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+7…"
              />
            </div>
          )}

          {required.includes('address') && (
            <div className="address-edit-page__field">
              <label className="address-edit-page__label" htmlFor="address">
                Адрес
              </label>
              <textarea
                id="address"
                className="address-edit-page__input-textarea"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Город, улица, дом, квартира"
              />
            </div>
          )}

          {required.includes('pickup_point_code') && (
            <div className="address-edit-page__field">
              <span className="address-edit-page__label">ПВЗ CDEK</span>
              <button
                type="button"
                className="address-edit-page__pvz-button"
                onClick={() => {
                  const editState = {
                    selectedCode,
                    recipientName,
                    phone,
                    address,
                    pickupPointCode,
                    pickupPointLabel,
                    cdekPostalCode,
                    cdekCityCode,
                    selectedLocalPickupId,
                    preset: editPreset,
                  };
                  try {
                    sessionStorage.setItem(
                      ADDRESS_EDIT_STORAGE_KEY,
                      JSON.stringify(editState)
                    );
                  } catch (_) {}
                  navigate('/main/profile/addresses/cdek-pvz', {
                    state: { fromAddressEdit: true, editState },
                  });
                }}
              >
                <span
                  className={
                    'address-edit-page__pvz-label' +
                    (!pickupPointLabel ? ' address-edit-page__pvz-placeholder' : '')
                  }
                >
                  {pickupPointLabel || 'Выбрать ПВЗ на карте'}
                </span>
                <span className="address-edit-page__pvz-arrow">{SVG_ARROW_RIGHT}</span>
              </button>
            </div>
          )}
          {selectedCode === 'PICKUP_LOCAL' && localPickupPoints.length > 0 && (
            <div className="address-edit-page__field">
              <span className="address-edit-page__label">ПВЗ г. Уссурийск</span>
              {isEditMode ? (
                <div className="address-edit-page__readonly-address" aria-readonly>
                  {address || 'Адрес не указан'}
                </div>
              ) : (
                <div className="address-edit-page__methods">
                  {localPickupPoints.map((point) => (
                    <button
                      key={point.id}
                      type="button"
                      className={
                        'address-edit-page__method-btn' +
                        (selectedLocalPickupId === point.id ? ' address-edit-page__method-btn--active' : '')
                      }
                      onClick={() => setSelectedLocalPickupId(point.id)}
                    >
                      {point.address}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </form>
      )}

      <div
        className={
          'address-edit-page__footer' + (keyboardOpen ? ' address-edit-page__footer--hidden' : '')
        }
      >
        <div className="address-edit-page__footer-inner">
          {isEditMode && (
            <Button
              type="button"
              size="small"
              variant="secondary"
              disabled={deleting}
              className="address-edit-page__delete-btn"
              onClick={handleDelete}
            >
              Удалить
            </Button>
          )}
          <Button
            type="submit"
            size="small"
            variant="primary"
            disabled={!isValid || saving}
            className="cart-page__checkout-btn"
            onClick={handleSubmit}
          >
            Готово
          </Button>
        </div>
      </div>
    </div>
  );
}

