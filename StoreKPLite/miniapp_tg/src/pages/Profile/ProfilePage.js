import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getUserDeliveryPresets } from '../../api/delivery';
import { getOrders, fetchLikedSummary } from '../../api/products';
import { ensureHttps } from '../../utils/url';
import { fetchWithAuthRelogin } from '../../utils/sessionRelogin';
import { getAuthChannel } from '../../utils/miniappAccessToken';
import { getUsersApiBase } from '../../utils/miniappAdminOnly';
import { fileToSquareAvatarJpeg } from '../../utils/cropCenterSquareJpeg';
import ProfileAvatarEditorModal from '../../components/ProfileAvatarEditorModal';
import AvatarWithFallback from '../../components/AvatarWithFallback';
import { hasTelegramWebAppInitData } from '../../utils/telegramEnvironment';
import './ProfilePage.css';

const SVG_PENCIL = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M11.4144 1.79297L14.2075 4.58547C14.3004 4.67834 14.3741 4.78858 14.4243 4.90993C14.4746 5.03127 14.5005 5.16132 14.5005 5.29266C14.5005 5.424 14.4746 5.55406 14.4243 5.6754C14.3741 5.79674 14.3004 5.90699 14.2075 5.99985L7.2075 12.9999L6.19758 13.9999H3C2.73479 13.9999 2.48043 13.8945 2.2929 13.707C2.10536 13.5194 2.00001 13.2651 2.00001 12.9999V10.2067C1.99959 10.0754 2.02528 9.94521 2.0756 9.82386C2.12593 9.70251 2.19987 9.59237 2.29313 9.49985L10 1.79297C10.0929 1.70009 10.2031 1.62641 10.3245 1.57614C10.4458 1.52587 10.5758 1.5 10.7072 1.5C10.8385 1.5 10.9686 1.52587 11.0899 1.57614C11.2113 1.62641 11.3215 1.70009 11.4144 1.79297ZM3 12.9999H5.79313L11.2931 7.49985L8.5 4.70672L3 10.2067V12.9999ZM9.2075 3.99985L12 6.79297L13.5 5.29297L10.7075 2.49985L9.2075 3.99985Z"
      fill="#525252"
    />
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 6.79297L9.2075 3.99985L10.7075 2.49985L13.5 5.29297L12 6.79297Z"
      fill="#525252"
    />
  </svg>
);

const SVG_LOCATION = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path
      d="M8 4C7.50555 4 7.0222 4.14662 6.61107 4.42133C6.19995 4.69603 5.87952 5.08648 5.6903 5.54329C5.50108 6.00011 5.45157 6.50277 5.54804 6.98773C5.6445 7.47268 5.8826 7.91814 6.23223 8.26777C6.58186 8.6174 7.02732 8.8555 7.51227 8.95196C7.99723 9.04843 8.49989 8.99892 8.95671 8.8097C9.41352 8.62048 9.80397 8.30005 10.0787 7.88893C10.3534 7.4778 10.5 6.99445 10.5 6.5C10.5 5.83696 10.2366 5.20107 9.76777 4.73223C9.29893 4.26339 8.66304 4 8 4ZM8 8C7.70333 8 7.41332 7.91203 7.16664 7.7472C6.91997 7.58238 6.72771 7.34811 6.61418 7.07403C6.50065 6.79994 6.47094 6.49834 6.52882 6.20736C6.5867 5.91639 6.72956 5.64912 6.93934 5.43934C7.14912 5.22956 7.41639 5.0867 7.70736 5.02882C7.99834 4.97094 8.29994 5.00065 8.57403 5.11418C8.84811 5.22771 9.08238 5.41997 9.2472 5.66664C9.41203 5.91332 9.5 6.20333 9.5 6.5C9.5 6.89782 9.34196 7.27936 9.06066 7.56066C8.77936 7.84196 8.39782 8 8 8ZM8 1C6.54182 1.00165 5.14383 1.58165 4.11274 2.61274C3.08165 3.64383 2.50165 5.04182 2.5 6.5C2.5 8.4625 3.40688 10.5425 5.125 12.5156C5.89701 13.4072 6.76591 14.2101 7.71562 14.9094C7.7997 14.9683 7.89985 14.9999 8.0025 14.9999C8.10515 14.9999 8.20531 14.9683 8.28938 14.9094C9.23734 14.2098 10.1046 13.4069 10.875 12.5156C12.5906 10.5425 13.5 8.4625 13.5 6.5C13.4983 5.04182 12.9184 3.64383 11.8873 2.61274C10.8562 1.58165 9.45818 1.00165 8 1ZM8 13.875C6.96688 13.0625 3.5 10.0781 3.5 6.5C3.5 5.30653 3.97411 4.16193 4.81802 3.31802C5.66193 2.47411 6.80653 2 8 2C9.19347 2 10.3381 2.47411 11.182 3.31802C12.0259 4.16193 12.5 5.30653 12.5 6.5C12.5 10.0769 9.03312 13.0625 8 13.875Z"
      fill="#525252"
    />
  </svg>
);

const SVG_ORDERS = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path
      d="M13.98 4.13414L8.48 1.12477C8.33305 1.04357 8.16789 1.00098 8 1.00098C7.83211 1.00098 7.66695 1.04357 7.52 1.12477L2.02 4.13539C1.86293 4.22133 1.73181 4.34787 1.64034 4.50178C1.54888 4.6557 1.50041 4.83135 1.5 5.01039V10.9879C1.50041 11.1669 1.54888 11.3426 1.64034 11.4965C1.73181 11.6504 1.86293 11.777 2.02 11.8629L7.52 14.8735C7.66695 14.9547 7.83211 14.9973 8 14.9973C8.16789 14.9973 8.33305 14.9547 8.48 14.8735L13.98 11.8629C14.1371 11.777 14.2682 11.6504 14.3597 11.4965C14.4511 11.3426 14.4996 11.1669 14.5 10.9879V5.01102C14.4999 4.83166 14.4516 4.65561 14.3601 4.50134C14.2686 4.34706 14.1373 4.22024 13.98 4.13414ZM8 1.99977L13.0212 4.74977L11.1606 5.76852L6.13875 3.01852L8 1.99977ZM8 7.49977L2.97875 4.74977L5.0975 3.58977L10.1187 6.33977L8 7.49977ZM2.5 5.62477L7.5 8.36102V13.7229L2.5 10.9885V5.62477ZM13.5 10.986L8.5 13.7229V8.36352L10.5 7.26914V9.49977C10.5 9.63238 10.5527 9.75955 10.6464 9.85332C10.7402 9.94709 10.8674 9.99977 11 9.99977C11.1326 9.99977 11.2598 9.94709 11.3536 9.85332C11.4473 9.75955 11.5 9.63238 11.5 9.49977V6.72164L13.5 5.62477V10.9854V10.986Z"
      fill="#525252"
    />
  </svg>
);

const SVG_HEART = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path
      d="M9.73438 2.1875C8.60508 2.1875 7.61633 2.67312 7 3.49398C6.38367 2.67312 5.39492 2.1875 4.26562 2.1875C3.36669 2.18851 2.50486 2.54606 1.86921 3.18171C1.23356 3.81736 0.876013 4.67919 0.875 5.57812C0.875 9.40625 6.55102 12.5048 6.79273 12.6328C6.85644 12.6671 6.92766 12.685 7 12.685C7.07234 12.685 7.14356 12.6671 7.20727 12.6328C7.44898 12.5048 13.125 9.40625 13.125 5.57812C13.124 4.67919 12.7664 3.81736 12.1308 3.18171C11.4951 2.54606 10.6333 2.18851 9.73438 2.1875ZM7 11.7469C6.00141 11.165 1.75 8.5143 1.75 5.57812C1.75087 4.91121 2.01619 4.27185 2.48777 3.80027C2.95935 3.32869 3.59871 3.06337 4.26562 3.0625C5.3293 3.0625 6.22234 3.62906 6.59531 4.53906C6.62827 4.6193 6.68435 4.68794 6.7564 4.73624C6.82846 4.78454 6.91325 4.81033 7 4.81033C7.08675 4.81033 7.17154 4.78454 7.2436 4.73624C7.31565 4.68794 7.37173 4.6193 7.40469 4.53906C7.77766 3.62742 8.6707 3.0625 9.73438 3.0625C10.4013 3.06337 11.0406 3.32869 11.5122 3.80027C11.9838 4.27185 12.2491 4.91121 12.25 5.57812C12.25 8.50992 7.9975 11.1645 7 11.7469Z"
      fill="#525252"
    />
  </svg>
);

function pluralizeAddress(count) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return 'адресов';
  if (n1 > 1 && n1 < 5) return 'адреса';
  if (n1 === 1) return 'адрес';
  return 'адресов';
}

function pluralizeOrder(count) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return 'заказов';
  if (n1 > 1 && n1 < 5) return 'заказа';
  if (n1 === 1) return 'заказ';
  return 'заказов';
}

function pluralizeProduct(count) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return 'товаров';
  if (n1 > 1 && n1 < 5) return 'товара';
  if (n1 === 1) return 'товар';
  return 'товаров';
}

function ProfileRow({ icon, badgeText, text, onClick }) {
  return (
    <button type="button" className="profile-addresses" onClick={onClick}>
      <div className="profile-addresses__row">
        <span className="profile-addresses__icon">{icon}</span>
        <div className="profile-addresses__badge">
          <span className="profile-addresses__badge-text">{badgeText}</span>
        </div>
        <div className="profile-addresses__text">{text}</div>
      </div>
    </button>
  );
}

const GENDER_OPTIONS = [
  { value: '', label: 'Не указан' },
  { value: 'male', label: 'Мужской' },
  { value: 'female', label: 'Женский' },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, token, login, logout, refreshUser, updateFromProfileResponse } = useAuth();
  const fileInputRef = React.useRef(null);
  const [avatarModalOpen, setAvatarModalOpen] = useState(false);
  const [avatarPreviewUrl, setAvatarPreviewUrl] = useState(null);
  const [avatarBlob, setAvatarBlob] = useState(null);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarModalError, setAvatarModalError] = useState(null);
  const [addressesCount, setAddressesCount] = useState(0);
  const [ordersCount, setOrdersCount] = useState(0);
  const [likedCount, setLikedCount] = useState(null);
  const [genderSaving, setGenderSaving] = useState(false);
  const [genderDropdownOpen, setGenderDropdownOpen] = useState(false);
  const genderDropdownRef = React.useRef(null);

  const displayAvatarUrl = useMemo(() => {
    const u = user?.avatar_url;
    return u ? ensureHttps(u) : null;
  }, [user?.avatar_url]);

  const revokeAvatarPreview = React.useCallback(() => {
    if (avatarPreviewUrl) {
      URL.revokeObjectURL(avatarPreviewUrl);
    }
    setAvatarPreviewUrl(null);
    setAvatarBlob(null);
  }, [avatarPreviewUrl]);

  const closeAvatarModal = React.useCallback(() => {
    if (avatarUploading) return;
    revokeAvatarPreview();
    setAvatarModalOpen(false);
    setAvatarModalError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [avatarUploading, revokeAvatarPreview]);

  const openAvatarPicker = React.useCallback(() => {
    if (!token) return;
    setAvatarModalError(null);
    fileInputRef.current?.click();
  }, [token]);

  const onAvatarFile = React.useCallback(
    async (e) => {
      const f = e.target.files?.[0];
      e.target.value = '';
      if (!f) return;
      setAvatarModalError(null);
      try {
        const blob = await fileToSquareAvatarJpeg(f, 384, 0.88);
        revokeAvatarPreview();
        const url = URL.createObjectURL(blob);
        setAvatarPreviewUrl(url);
        setAvatarBlob(blob);
        setAvatarModalOpen(true);
      } catch {
        setAvatarPreviewUrl(null);
        setAvatarBlob(null);
        setAvatarModalError('Не удалось открыть изображение');
        setAvatarModalOpen(true);
      }
    },
    [revokeAvatarPreview]
  );

  const confirmAvatarUpload = React.useCallback(async () => {
    if (!token || !avatarBlob) return;
    setAvatarUploading(true);
    setAvatarModalError(null);
    try {
      const base = getUsersApiBase();
      const fd = new FormData();
      fd.append('file', avatarBlob, 'avatar.jpg');
      const opts = {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      };
      if (getAuthChannel() === 'browser') {
        opts.credentials = 'include';
      }
      const res = await fetchWithAuthRelogin(`${base}/users/me/profile-avatar`, opts);
      if (!res.ok) {
        setAvatarModalError(
          res.status === 400 ? 'Неподходящий файл или слишком большой' : `Ошибка ${res.status}`
        );
        return;
      }
      const data = await res.json();
      updateFromProfileResponse(data);
      closeAvatarModal();
    } catch {
      setAvatarModalError('Не удалось отправить');
    } finally {
      setAvatarUploading(false);
    }
  }, [token, avatarBlob, updateFromProfileResponse, closeAvatarModal]);

  const clearProfileAvatar = React.useCallback(async () => {
    if (!token || !user?.profile_avatar_url) return;
    try {
      const base = getUsersApiBase();
      const opts = {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      };
      if (getAuthChannel() === 'browser') {
        opts.credentials = 'include';
      }
      const res = await fetchWithAuthRelogin(`${base}/users/me/profile-avatar`, opts);
      if (res.ok) {
        const data = await res.json();
        updateFromProfileResponse(data);
      }
    } catch {
      /* ignore */
    }
  }, [token, user?.profile_avatar_url, updateFromProfileResponse]);

  useEffect(() => {
    return () => {
      if (avatarPreviewUrl) URL.revokeObjectURL(avatarPreviewUrl);
    };
  }, [avatarPreviewUrl]);

  useEffect(() => {
    async function loadAddresses() {
      try {
        const list = await getUserDeliveryPresets();
        setAddressesCount(Array.isArray(list) ? list.length : 0);
      } catch {
        setAddressesCount(0);
      }
    }
    loadAddresses();
  }, []);

  useEffect(() => {
    async function loadOrders() {
      try {
        const list = await getOrders();
        setOrdersCount(Array.isArray(list) ? list.length : 0);
      } catch {
        setOrdersCount(0);
      }
    }
    loadOrders();
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadLikedCount() {
      const key = user?.id != null ? `likesSummaryV1:like:${user.id}` : null;
      let knownRev = null;
      if (key) {
        try {
          const raw = sessionStorage.getItem(key);
          if (raw) {
            const j = JSON.parse(raw);
            if (j && typeof j.rev === 'number') knownRev = j.rev;
          }
        } catch {
          /* ignore */
        }
      }
      try {
        const { total, rev } = await fetchLikedSummary('like', knownRev);
        if (cancelled) return;
        if (key) {
          try {
            sessionStorage.setItem(key, JSON.stringify({ rev, total }));
          } catch {
            /* ignore */
          }
        }
        setLikedCount(typeof total === 'number' ? total : 0);
      } catch {
        if (!cancelled) setLikedCount(0);
      }
    }
    loadLikedCount();
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  useEffect(() => {
    if (!genderDropdownOpen) return;
    const handleClickOutside = (e) => {
      if (genderDropdownRef.current && !genderDropdownRef.current.contains(e.target)) {
        setGenderDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [genderDropdownOpen]);

  const displayName = useMemo(() => {
    if (hasTelegramWebAppInitData()) {
      const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
      if (tgUser?.first_name) return tgUser.first_name;
      if (tgUser?.username) return tgUser.username;
    }
    const fn = (user?.firstname || '').trim();
    if (fn) return fn;
    const un = (user?.username || '').trim();
    if (un) return un;
    return 'Пользователь';
  }, [user?.firstname, user?.username]);

  const phone = user?.country_code && user?.phone_local
    ? `${user.country_code} ${user.phone_local}`
    : user?.phone_local || 'Не указан';

  const genderLabel = useMemo(() => {
    const g = user?.gender;
    return GENDER_OPTIONS.find((o) => o.value === (g || ''))?.label ?? 'Не указан';
  }, [user?.gender]);

  const saveGender = async (value) => {
    if (!token) return;
    setGenderSaving(true);
    setGenderDropdownOpen(false);
    try {
      const base = getUsersApiBase();
      const res = await fetchWithAuthRelogin(`${base}/users/me`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ gender: value || '' }),
      });
      if (res.ok) {
        const data = await res.json();
        const initData = window.Telegram?.WebApp?.initData;
        if (hasTelegramWebAppInitData() && initData) {
          await logout();
          const reloginOk = await login(initData);
          if (!reloginOk) updateFromProfileResponse(data);
        } else {
          updateFromProfileResponse(data);
        }
      }
    } catch {
      /* ignore */
    } finally {
      setGenderSaving(false);
    }
  };

  const addressesText =
    addressesCount > 0 ? `${addressesCount} ${pluralizeAddress(addressesCount)}` : 'Нет адресов';
  const ordersText =
    ordersCount > 0 ? `${ordersCount} ${pluralizeOrder(ordersCount)}` : 'Нет заказов';
  const likedText =
    likedCount === null
      ? 'Загрузка…'
      : likedCount === 0
        ? 'Нет товаров'
        : `${likedCount} ${pluralizeProduct(likedCount)}`;

  const openBotForPhone = () => {
    const tg = window.Telegram?.WebApp;
    const rawUsername = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'MatchWear_bot';
    const botUsername = String(rawUsername).replace(/^@+/, '').trim() || 'MatchWear_bot';
    // Для перехода именно в чат с ботом нужен start, а не startapp.
    const link = `https://t.me/${botUsername}?start=share_phone`;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(link);
    } else {
      window.open(link, '_blank');
    }
  };

  // Пока номер не добавлен — опрашиваем профиль, чтобы подтянуть данные после возврата из бота
  const hasPhone = Boolean(user?.phone_local);
  useEffect(() => {
    if (hasPhone || !user || !refreshUser) return;
    const POLL_MS = 4000;
    const id = setInterval(() => refreshUser(), POLL_MS);
    return () => clearInterval(id);
  }, [hasPhone, user, refreshUser]);

  // При возврате в приложение (видимость вкладки) один раз обновляем профиль, если номера ещё нет
  useEffect(() => {
    if (hasPhone || !refreshUser) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshUser();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [hasPhone, refreshUser]);

  return (
    <div className="profile-page page-container">
      {avatarModalOpen ? (
        <ProfileAvatarEditorModal
          previewUrl={avatarPreviewUrl}
          uploading={avatarUploading}
          errorText={avatarModalError}
          onClose={closeAvatarModal}
          onConfirm={confirmAvatarUpload}
        />
      ) : null}
      <div className="profile-header-block">
        <div className="profile-header">
          <div className="profile-header__avatar-wrap">
            <button
              type="button"
              className="profile-header__avatar-btn"
              onClick={openAvatarPicker}
              aria-label="Загрузить фото профиля"
              disabled={!token}
            >
              <AvatarWithFallback
                src={displayAvatarUrl}
                seed={user?.id}
                className="profile-header__avatar-img"
                alt=""
              />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              className="profile-header__avatar-file"
              onChange={onAvatarFile}
              aria-hidden
              tabIndex={-1}
            />
          </div>
          <div className="profile-header__bar">
            <span className="profile-header__name">{displayName}</span>
          </div>
        </div>
        {user?.profile_avatar_url ? (
          <button type="button" className="profile-avatar-reset-link" onClick={clearProfileAvatar}>
            Показывать фото из Telegram
          </button>
        ) : null}
      </div>

      <div className="profile-fields">
        <div className="profile-field">
          <div className="profile-field__label">Номер телефона:</div>
          <div className="profile-field__value-row">
            <div className="profile-field__value">{phone}</div>
            <button
              type="button"
              className="profile-field__icon-btn"
              aria-label="Указать номер через бота"
              onClick={openBotForPhone}
            >
              {SVG_PENCIL}
            </button>
          </div>
        </div>
        <div className="profile-field profile-field--with-dropdown" ref={genderDropdownRef}>
          <div className="profile-field__label">Пол:</div>
          <div className="profile-field__value-row">
            <button
              type="button"
              className="profile-field__value-btn"
              onClick={() => !genderSaving && setGenderDropdownOpen((v) => !v)}
              disabled={genderSaving}
              aria-expanded={genderDropdownOpen}
              aria-haspopup="listbox"
              aria-label="Выбрать пол"
            >
              <span className="profile-field__value">{genderLabel}</span>
            </button>
            <button
              type="button"
              className="profile-field__icon-btn"
              aria-label="Выбрать пол"
              onClick={() => !genderSaving && setGenderDropdownOpen((v) => !v)}
              disabled={genderSaving}
            >
              {SVG_PENCIL}
            </button>
          </div>
          {genderDropdownOpen && (
            <div
              className="profile-field__dropdown"
              role="listbox"
              aria-label="Пол"
            >
              {GENDER_OPTIONS.map((opt) => (
                <button
                  key={opt.value || 'none'}
                  type="button"
                  role="option"
                  aria-selected={(user?.gender ?? '') === opt.value}
                  className="profile-field__dropdown-option"
                  onClick={() => saveGender(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <ProfileRow
        icon={SVG_LOCATION}
        badgeText="Адреса"
        text={addressesText}
        onClick={() => navigate('/main/profile/addresses')}
      />
      <ProfileRow
        icon={SVG_ORDERS}
        badgeText="Заказы"
        text={ordersText}
        onClick={() => navigate('/main/profile/orders')}
      />
      <ProfileRow
        icon={SVG_HEART}
        badgeText="Понравившиеся"
        text={likedText}
        onClick={() => navigate('/main/profile/liked')}
      />
    </div>
  );
}

