import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTabBarVisibility } from '../../contexts/TabBarVisibilityContext';
import { getCdekPickupPoints } from '../../api/delivery';
import { hasTelegramWebAppInitData, isTelegramWebAppEnvironment } from '../../utils/telegramEnvironment';
import { useBrowserBackHandlerRef } from '../../contexts/BrowserBackHandlerRefContext';
import Button from '../../components/Button';
import './CdekPickupMapPage.css';

const CLOSE_ICON_SVG = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M10.3538 6.35375L8.70688 8L10.3538 9.64625C10.4002 9.69271 10.4371 9.74786 10.4622 9.80855C10.4873 9.86925 10.5003 9.9343 10.5003 10C10.5003 10.0657 10.4873 10.1308 10.4622 10.1914C10.4371 10.2521 10.4002 10.3073 10.3538 10.3538C10.3073 10.4002 10.2521 10.4371 10.1915 10.4622C10.1308 10.4873 10.0657 10.5003 10 10.5003C9.93431 10.5003 9.86925 10.4873 9.80855 10.4622C9.74786 10.4371 9.69271 10.4002 9.64625 10.3538L8 8.70687L6.35375 10.3538C6.3073 10.4002 6.25215 10.4371 6.19145 10.4622C6.13075 10.4873 6.0657 10.5003 6 10.5003C5.93431 10.5003 5.86925 10.4873 5.80855 10.4622C5.74786 10.4371 5.69271 10.4002 5.64625 10.3538C5.5998 10.3073 5.56295 10.2521 5.53781 10.1914C5.51266 10.1308 5.49972 10.0657 5.49972 10C5.49972 9.9343 5.51266 9.86925 5.53781 9.80855C5.56295 9.74786 5.5998 9.69271 5.64625 9.64625L7.29313 8L5.64625 6.35375C5.55243 6.25993 5.49972 6.13268 5.49972 6C5.49972 5.86732 5.55243 5.74007 5.64625 5.64625C5.74007 5.55243 5.86732 5.49972 6 5.49972C6.13268 5.49972 6.25993 5.55243 6.35375 5.64625L8 7.29313L9.64625 5.64625C9.69271 5.59979 9.74786 5.56294 9.80855 5.5378C9.86925 5.51266 9.93431 5.49972 10 5.49972C10.0657 5.49972 10.1308 5.51266 10.1915 5.5378C10.2521 5.56294 10.3073 5.59979 10.3538 5.64625C10.4002 5.6927 10.4371 5.74786 10.4622 5.80855C10.4873 5.86925 10.5003 5.9343 10.5003 6C10.5003 6.0657 10.4873 6.13075 10.4622 6.19145C10.4371 6.25214 10.4002 6.3073 10.3538 6.35375ZM14.5 8C14.5 9.28558 14.1188 10.5423 13.4046 11.6112C12.6903 12.6801 11.6752 13.5132 10.4874 14.0052C9.29973 14.4972 7.99279 14.6259 6.73192 14.3751C5.47104 14.1243 4.31285 13.5052 3.40381 12.5962C2.49477 11.6872 1.8757 10.529 1.6249 9.26809C1.37409 8.00721 1.50282 6.70028 1.99479 5.51256C2.48676 4.32484 3.31988 3.30968 4.3888 2.59545C5.45772 1.88122 6.71442 1.5 8 1.5C9.72335 1.50182 11.3756 2.18722 12.5942 3.40582C13.8128 4.62441 14.4982 6.27665 14.5 8ZM13.5 8C13.5 6.9122 13.1774 5.84883 12.5731 4.94436C11.9687 4.03989 11.1098 3.33494 10.1048 2.91866C9.09977 2.50238 7.9939 2.39346 6.92701 2.60568C5.86011 2.8179 4.8801 3.34172 4.11092 4.11091C3.34173 4.8801 2.8179 5.86011 2.60568 6.927C2.39347 7.9939 2.50238 9.09977 2.91867 10.1048C3.33495 11.1098 4.0399 11.9687 4.94437 12.5731C5.84884 13.1774 6.91221 13.5 8 13.5C9.45819 13.4983 10.8562 12.9184 11.8873 11.8873C12.9184 10.8562 13.4983 9.45818 13.5 8Z" fill="currentColor" />
  </svg>
);

const YANDEX_MAPS_API_KEY = process.env.REACT_APP_YANDEX_MAPS_API_KEY || '';
const RADIUS_KM = 50;
const MOSCOW_CENTER = { latitude: 55.7558, longitude: 37.6173 };
const ADDRESS_EDIT_STORAGE_KEY = 'addressEditFormState';

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

const LOCATION_TIMEOUT_MS = 10000;

/**
 * Запрос геолокации.
 * В мини-аппе Telegram — только LocationManager (официальный API: getLocation(callback) с одним аргументом — null при отказе, LocationData при успехе).
 * В браузере (без TG) — navigator.geolocation для разработки.
 */
function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    let settled = false;
    const once = (fn) => (...args) => {
      if (settled) return;
      settled = true;
      fn(...args);
    };

    const tg = window.Telegram?.WebApp;
    const locationManager = tg?.LocationManager;
    const inTg = hasTelegramWebAppInitData();

    if (inTg && locationManager && typeof locationManager.init === 'function' && typeof locationManager.getLocation === 'function') {
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error('Разрешите доступ к геолокации в настройках Telegram или повторите попытку'));
      }, LOCATION_TIMEOUT_MS);

      const doGetLocation = () => {
        if (settled) return;
        if (locationManager.isLocationAvailable === false) {
          clearTimeout(timer);
          settled = true;
          reject(new Error('Геолокация недоступна на этом устройстве'));
          return;
        }
        locationManager.getLocation((locationData) => {
          if (settled) return;
          clearTimeout(timer);
          if (!locationData || typeof locationData.latitude !== 'number' || typeof locationData.longitude !== 'number') {
            settled = true;
            reject(new Error('Доступ к геолокации не разрешён. Включите в настройках бота (Бот → Разрешить доступ к геолокации).'));
            return;
          }
          once(resolve)({ latitude: locationData.latitude, longitude: locationData.longitude });
        });
      };

      if (locationManager.isInited) {
        doGetLocation();
      } else {
        locationManager.init(doGetLocation);
      }
      return;
    }

    if (!inTg && navigator.geolocation) {
      tryBrowserGeolocation(once(resolve), once(reject));
      return;
    }

    if (inTg) {
      reject(new Error('Геолокация недоступна в этой версии приложения'));
    } else {
      reject(new Error('Геолокация недоступна'));
    }
  });
}

function tryBrowserGeolocation(resolve, reject) {
  if (!navigator.geolocation) {
    reject(new Error('Геолокация недоступна'));
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
    (err) => reject(new Error(err.message || 'Не удалось получить геолокацию')),
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
  );
}

/**
 * Из длинного названия типа "Уссурийский городской округ" получаем короткое для СДЭК: "Уссурийск".
 * Справочник СДЭК знает города по краткому имени (Уссурийск, Москва), а не по округам.
 */
function deriveCityNameForCdek(longName) {
  if (!longName || typeof longName !== 'string') return null;
  const s = longName.trim();
  if (!s) return null;
  // "Уссурийский городской округ" → "Уссурийск"
  const t = s.replace(/\s*городской\s+округ\s*$/i, '').trim();
  if (t !== s) {
    const m = t.match(/^(.+?)(ский|ой|ий|ый)$/);
    if (m) {
      const stem = m[1];
      if (m[2] === 'ский') return stem + 'ск';
      if (m[2] === 'ий' || m[2] === 'ой') return stem + 'ийск';
      if (m[2] === 'ый') return stem + 'ск';
    }
    return t;
  }
  // "Нижегородская область" и т.п. — не подставляем
  return null;
}

/**
 * Обратное геокодирование: координаты → список вариантов названия города для запроса к СДЭК.
 * Возвращает массив строк: сначала точные locality, потом производные от area (напр. Уссурийск из округа).
 */
async function reverseGeocodeCityCandidates(lat, lon) {
  const url = `https://geocode-maps.yandex.ru/v1/?apikey=${YANDEX_MAPS_API_KEY}&geocode=${lon},${lat}&lang=ru_RU&format=json&results=5`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Ошибка геокодирования');
  const data = await res.json();
  const coll = data?.response?.GeoObjectCollection;
  if (!coll || !Array.isArray(coll.featureMember)) return [];

  const seen = new Set();
  const add = (name) => {
    if (name && typeof name === 'string') {
      const n = name.trim();
      if (n && !seen.has(n)) {
        seen.add(n);
        return n;
      }
    }
    return null;
  };

  for (const member of coll.featureMember) {
    const obj = member?.GeoObject;
    if (!obj) continue;
    const meta = obj?.metaDataProperty?.GeocoderMetaData;
    const comp = meta?.Address?.Components || meta?.address?.Components;
    if (!Array.isArray(comp)) continue;

    for (const c of comp) {
      if (c.kind === 'locality' && c.name) {
        add(c.name);
      }
      if (c.kind === 'area' && c.name) {
        add(c.name);
        const derived = deriveCityNameForCdek(c.name);
        if (derived) add(derived);
      }
    }
  }

  const first = coll.featureMember[0]?.GeoObject;
  const meta = first?.metaDataProperty?.GeocoderMetaData;
  const text = meta?.text;
  if (text) add(text);

  return Array.from(seen);
}

const DELIVERY_TYPE_LABEL = 'ПВЗ СДЭК';

/**
 * Формирует объект выбранного ПВЗ для передачи в форму: код для отправки/расчётов и полный адрес для отображения и сохранения в пресете.
 */
function buildSelectedPickupPointPayload(point) {
  if (!point) return undefined;
  const fullAddress = point.address || point.name || DELIVERY_TYPE_LABEL;
  const rawCc = point.city_code;
  const cityCode =
    rawCc != null && String(rawCc).trim() !== ''
      ? Number.parseInt(String(rawCc).trim(), 10)
      : null;
  return {
    code: point.code ?? '',
    label: fullAddress,
    address: point.address ?? '',
    name: point.name ?? '',
    work_time: point.work_time ?? '',
    city: point.city ?? '',
    postal_code: (point.postal_code != null && String(point.postal_code).trim()) || '',
    city_code: Number.isFinite(cityCode) ? cityCode : null,
  };
}

function createMarkerElement(point, isSelected, onSelect) {
  const wrap = document.createElement('div');
  wrap.className = 'cdek-map-marker-wrap';

  const balloon = document.createElement('div');
  balloon.className = 'cdek-map-balloon' + (isSelected ? ' cdek-map-balloon--selected' : '');

  const nameEl = document.createElement('div');
  nameEl.className = 'cdek-map-balloon__name';
  nameEl.textContent = DELIVERY_TYPE_LABEL;

  const infoEl = document.createElement('div');
  infoEl.className = 'cdek-map-balloon__info';
  infoEl.textContent = point.address_short || point.address || point.work_time || '';

  balloon.appendChild(nameEl);
  balloon.appendChild(infoEl);
  wrap.appendChild(balloon);

  const iconWrap = document.createElement('div');
  iconWrap.className = 'cdek-map-marker-icon';
  iconWrap.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 6C11.2583 6 10.5333 6.21993 9.91661 6.63199C9.29993 7.04404 8.81928 7.62971 8.53545 8.31494C8.25162 9.00016 8.17736 9.75416 8.32205 10.4816C8.46675 11.209 8.8239 11.8772 9.34835 12.4017C9.8728 12.9261 10.541 13.2833 11.2684 13.4279C11.9958 13.5726 12.7498 13.4984 13.4351 13.2145C14.1203 12.9307 14.706 12.4501 15.118 11.8334C15.5301 11.2167 15.75 10.4917 15.75 9.75C15.75 8.75544 15.3549 7.80161 14.6517 7.09835C13.9484 6.39509 12.9946 6 12 6ZM12 12C11.555 12 11.12 11.868 10.75 11.6208C10.38 11.3736 10.0916 11.0222 9.92127 10.611C9.75097 10.1999 9.70642 9.7475 9.79323 9.31105C9.88005 8.87459 10.0943 8.47368 10.409 8.15901C10.7237 7.84434 11.1246 7.63005 11.561 7.54323C11.9975 7.45642 12.4499 7.50097 12.861 7.67127C13.2722 7.84157 13.6236 8.12996 13.8708 8.49997C14.118 8.86998 14.25 9.30499 14.25 9.75C14.25 10.3467 14.0129 10.919 13.591 11.341C13.169 11.7629 12.5967 12 12 12ZM12 1.5C9.81273 1.50248 7.71575 2.37247 6.16911 3.91911C4.62247 5.46575 3.75248 7.56273 3.75 9.75C3.75 12.6938 5.11031 15.8138 7.6875 18.7734C8.84552 20.1108 10.1489 21.3151 11.5734 22.3641C11.6995 22.4524 11.8498 22.4998 12.0037 22.4998C12.1577 22.4998 12.308 22.4524 12.4341 22.3641C13.856 21.3147 15.1568 20.1104 16.3125 18.7734C18.8859 15.8138 20.25 12.6938 20.25 9.75C20.2475 7.56273 19.3775 5.46575 17.8309 3.91911C16.2843 2.37247 14.1873 1.50248 12 1.5ZM12 20.8125C10.4503 19.5938 5.25 15.1172 5.25 9.75C5.25 7.95979 5.96116 6.2429 7.22703 4.97703C8.4929 3.71116 10.2098 3 12 3C13.7902 3 15.5071 3.71116 16.773 4.97703C18.0388 6.2429 18.75 7.95979 18.75 9.75C18.75 15.1153 13.5497 19.5938 12 20.8125Z" fill="black"/><path fill-rule="evenodd" clip-rule="evenodd" d="M5.25 9.75C5.25 15.1172 10.4503 19.5938 12 20.8125C13.5497 19.5938 18.75 15.1153 18.75 9.75C18.75 7.95979 18.0388 6.2429 16.773 4.97703C15.5071 3.71116 13.7902 3 12 3C10.2098 3 8.4929 3.71116 7.22703 4.97703C5.96116 6.2429 5.25 7.95979 5.25 9.75ZM12 6C11.2583 6 10.5333 6.21993 9.91661 6.63199C9.29993 7.04404 8.81928 7.62971 8.53545 8.31494C8.25162 9.00016 8.17736 9.75416 8.32205 10.4816C8.46675 11.209 8.8239 11.8772 9.34835 12.4017C9.8728 12.9261 10.541 13.2833 11.2684 13.4279C11.9958 13.5726 12.7498 13.4984 13.4351 13.2145C14.1203 12.9307 14.706 12.4501 15.118 11.8334C15.5301 11.2167 15.75 10.4917 15.75 9.75C15.75 8.75544 15.3549 7.80161 14.6517 7.09835C13.9484 6.39509 12.9946 6 12 6Z" fill="black"/></svg>`;
  wrap.appendChild(iconWrap);

  wrap.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (typeof onSelect === 'function') onSelect(point);
  });
  wrap.style.pointerEvents = 'auto';
  wrap.style.cursor = 'pointer';

  return wrap;
}

const CLUSTER_SOURCE_ID = 'cdek-clusterer-source';

const YANDEX_MAPS_SCRIPT_ID = 'yandex-maps-api-v3';
const YANDEX_MAPS_READY_TIMEOUT_MS = 15000;

/**
 * Загружает API Яндекс.Карт 3.0 динамически (при открытии страницы ПВЗ).
 * Так Referer при запросе скрипта — текущий URL (miniapp.nixbi.ru), а не родительский фрейм Telegram.
 * Параметр csp=202512 — требование Яндекса для совместимости с обновлённым CSP (см. документацию API карт).
 * Возвращает Promise, который резолвится когда ymaps3 готов, или реджектится при ошибке/таймауте.
 */
function loadYandexMapsScript() {
  if (typeof window === 'undefined') return Promise.reject(new Error('No window'));
  if (window.ymaps3 && window.ymaps3.ready) {
    return Promise.race([
      Promise.resolve(window.ymaps3.ready),
      new Promise((_, rej) => setTimeout(() => rej(new Error('Таймаут загрузки карт')), YANDEX_MAPS_READY_TIMEOUT_MS)),
    ]);
  }

  const existing = document.getElementById(YANDEX_MAPS_SCRIPT_ID);
  if (existing) {
    const deadline = Date.now() + YANDEX_MAPS_READY_TIMEOUT_MS;
    const waitReady = () =>
      new Promise((resolve, reject) => {
        const check = () => {
          if (window.ymaps3 && window.ymaps3.ready) {
            Promise.resolve(window.ymaps3.ready).then(resolve).catch(reject);
            return;
          }
          if (Date.now() > deadline) {
            reject(new Error('Таймаут загрузки карт'));
            return;
          }
          setTimeout(check, 150);
        };
        check();
      });
    return waitReady();
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = YANDEX_MAPS_SCRIPT_ID;
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(YANDEX_MAPS_API_KEY)}&lang=ru_RU&csp=202512`;
    script.async = false;
    script.onload = () => {
      const ready = window.ymaps3 && window.ymaps3.ready;
      if (ready) {
        Promise.race([
          Promise.resolve(ready),
          new Promise((_, rej) => setTimeout(() => rej(new Error('Таймаут инициализации карт')), YANDEX_MAPS_READY_TIMEOUT_MS)),
        ]).then(resolve).catch(reject);
      } else {
        reject(new Error('API карт не инициализировался'));
      }
    };
    script.onerror = () => reject(new Error('Не удалось загрузить карты. Проверьте ключ и ограничения по Referer в кабинете Яндекса.'));
    document.head.appendChild(script);
  });
}

function createClusterElement(count) {
  const wrap = document.createElement('div');
  wrap.className = 'cdek-map-cluster';
  const inner = document.createElement('span');
  inner.className = 'cdek-map-cluster__count';
  inner.textContent = String(count);
  wrap.appendChild(inner);
  return wrap;
}

export default function CdekPickupStubPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTabBarVisible } = useTabBarVisibility();
  const browserBackHandlerRef = useBrowserBackHandlerRef();
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const clustererRef = useRef(null);
  const clustererLayerRef = useRef(null);
  const searchInputRef = useRef(null);
  const appliedCenterRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [userCoords, setUserCoords] = useState(null);
  const [points, setPoints] = useState([]);
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [citySearch, setCitySearch] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchCenter, setSearchCenter] = useState(null);
  const [mapError, setMapError] = useState(null);

  const editStateFromParent = location.state?.editState ?? null;
  const mapCenter = searchCenter || userCoords || MOSCOW_CENTER;

  const leaveCdekMap = useCallback(() => {
    const selectedPickupPoint = selectedPoint
      ? buildSelectedPickupPointPayload(selectedPoint)
      : undefined;
    if (selectedPickupPoint && editStateFromParent) {
      try {
        sessionStorage.setItem(
          ADDRESS_EDIT_STORAGE_KEY,
          JSON.stringify({
            ...editStateFromParent,
            pickupPointCode: selectedPickupPoint.code ?? '',
            pickupPointLabel: selectedPickupPoint.label ?? selectedPickupPoint.address ?? '',
            cdekPostalCode: selectedPickupPoint.postal_code ?? '',
            cdekCityCode:
              selectedPickupPoint.city_code != null && String(selectedPickupPoint.city_code).trim() !== ''
                ? String(selectedPickupPoint.city_code)
                : '',
          })
        );
      } catch (_) {}
    }
    navigate(-1, {
      state: {
        editState: editStateFromParent,
        preset: editStateFromParent?.preset ?? undefined,
        selectedPickupPoint,
      },
    });
  }, [navigate, editStateFromParent, selectedPoint]);

  useEffect(() => {
    setTabBarVisible(false);
    const tg = window.Telegram?.WebApp;
    const backButton = tg?.BackButton;
    if (!backButton) {
      return () => setTabBarVisible(true);
    }
    backButton.onClick(leaveCdekMap);
    backButton.show();
    return () => {
      backButton.offClick(leaveCdekMap);
      backButton.hide();
      setTabBarVisible(true);
    };
  }, [setTabBarVisible, leaveCdekMap]);

  useEffect(() => {
    if (isTelegramWebAppEnvironment()) return undefined;
    browserBackHandlerRef.current = leaveCdekMap;
    return () => {
      if (browserBackHandlerRef.current === leaveCdekMap) {
        browserBackHandlerRef.current = null;
      }
    };
  }, [browserBackHandlerRef, leaveCdekMap]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setUserCoords(null);
      setPoints([]);

      try {
        const pos = await getCurrentPosition();
        if (cancelled) return;
        setUserCoords(pos);

        const cityCandidates = await reverseGeocodeCityCandidates(pos.latitude, pos.longitude);
        if (cancelled) return;
        if (!cityCandidates.length) {
          setLoading(false);
          return;
        }

        let list = [];
        for (const city of cityCandidates) {
          try {
            const rawList = await getCdekPickupPoints({ city, limit: 100 });
            if (cancelled) return;
            list = Array.isArray(rawList) ? rawList : [];
            break;
          } catch (_) {
            continue;
          }
        }
        if (cancelled) return;

        const inRadius = list.filter((p) => {
          if (p.lat == null || p.lon == null) return false;
          return haversineKm(pos.latitude, pos.longitude, p.lat, p.lon) <= RADIUS_KM;
        });
        setPoints(inRadius);
      } catch (_) {
        if (!cancelled) {
          setUserCoords(null);
          setPoints([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const onSelectPoint = useCallback((point) => {
    setSelectedPoint((prev) => (prev?.code === point?.code ? prev : point));
  }, []);

  const confirmPickupPoint = useCallback(() => {
    if (!selectedPoint) return;
    leaveCdekMap();
  }, [selectedPoint, leaveCdekMap]);

  const handleCitySearch = useCallback(async () => {
    const city = citySearch.trim();
    if (!city) return;
    setSearchLoading(true);
    setSearchCenter(null);
    try {
      const rawList = await getCdekPickupPoints({ city, limit: 100 });
      const list = Array.isArray(rawList) ? rawList : [];
      setPoints(list);
      const withCoords = list.filter((p) => p.lat != null && p.lon != null);
      if (withCoords.length > 0) {
        const avgLat = withCoords.reduce((s, p) => s + p.lat, 0) / withCoords.length;
        const avgLon = withCoords.reduce((s, p) => s + p.lon, 0) / withCoords.length;
        setSearchCenter({ latitude: avgLat, longitude: avgLon });
      } else {
        setSearchCenter(null);
      }
    } catch (_) {
      setPoints([]);
      setSearchCenter(null);
    } finally {
      setSearchLoading(false);
    }
  }, [citySearch]);

  useEffect(() => {
    if (!mapRef.current) return;

    const container = mapRef.current;
    let mapInstance = mapInstanceRef.current;
    const selectedCode = selectedPoint?.code || null;
    const center = [mapCenter.longitude, mapCenter.latitude];

    setMapError(null);

    (async () => {
      try {
        if (!YANDEX_MAPS_API_KEY || !YANDEX_MAPS_API_KEY.trim()) {
          setMapError('Не задан ключ карт. В .env на сервере укажите REACT_APP_YANDEX_MAPS_API_KEY (или YANDEX_MAPS_API_KEY) и пересоберите: docker compose build --no-cache miniapp_tg');
          return;
        }
        await loadYandexMapsScript();
        if (!window.ymaps3) {
          setMapError('API карт недоступен');
          return;
        }

        async function initMap() {
      await window.ymaps3.ready;
      const ymaps3 = window.ymaps3;
      const { YMap, YMapDefaultSchemeLayer, YMapMarker } = ymaps3;

      let YMapFeatureDataSource;
      let YMapLayer;
      try {
        YMapFeatureDataSource = ymaps3.YMapFeatureDataSource;
        YMapLayer = ymaps3.YMapLayer;
      } catch (_) {}

      const removeClusterer = () => {
        const cur = clustererRef.current;
        if (!cur) return;
        try {
          mapInstance.removeChild(cur);
        } catch (_) {}
        clustererRef.current = null;
      };

      const zoom = 11;
      const centerChanged =
        !appliedCenterRef.current ||
        appliedCenterRef.current.latitude !== mapCenter.latitude ||
        appliedCenterRef.current.longitude !== mapCenter.longitude;

      if (!mapInstance) {
        const children = [
          new YMapDefaultSchemeLayer({}),
        ];
        if (YMapFeatureDataSource && YMapLayer) {
          children.push(new YMapFeatureDataSource({ id: CLUSTER_SOURCE_ID }));
          const layer = new YMapLayer({
            source: CLUSTER_SOURCE_ID,
            type: 'markers',
            zIndex: 1800,
          });
          children.push(layer);
          clustererLayerRef.current = true;
        }
        mapInstance = new YMap(container, { location: { center, zoom } }, children);
        mapInstanceRef.current = mapInstance;
        appliedCenterRef.current = { latitude: mapCenter.latitude, longitude: mapCenter.longitude };
      } else if (centerChanged) {
        try {
          if (typeof mapInstance.update === 'function') {
            mapInstance.update({ location: { center, zoom } });
          }
          appliedCenterRef.current = { latitude: mapCenter.latitude, longitude: mapCenter.longitude };
        } catch (_) {}
      }

      removeClusterer();

      const withCoords = points.filter((p) => p.lat != null && p.lon != null);
      if (withCoords.length === 0) return;

      if (!YMapFeatureDataSource || !YMapLayer) {
        const { YMapDefaultFeaturesLayer } = ymaps3;
        if (YMapDefaultFeaturesLayer) {
          try {
            mapInstance.addChild(new YMapDefaultFeaturesLayer({}));
          } catch (_) {}
        }
        const toAdd = [];
        withCoords.forEach((point) => {
          const el = createMarkerElement(point, point.code === selectedCode, onSelectPoint);
          const marker = new YMapMarker({ coordinates: [point.lon, point.lat] }, el);
          mapInstance.addChild(marker);
          toAdd.push(marker);
        });
        clustererRef.current = toAdd.length ? { markers: toAdd, isLegacy: true } : null;
        return;
      }

      try {
        ymaps3.import.registerCdn(
          'https://cdn.jsdelivr.net/npm/{package}',
          '@yandex/ymaps3-clusterer@latest'
        );
      } catch (_) {}

      let YMapClusterer;
      let clusterByGrid;
      try {
        const clustererModule = await ymaps3.import('@yandex/ymaps3-clusterer');
        YMapClusterer = clustererModule.YMapClusterer;
        clusterByGrid = clustererModule.clusterByGrid;
      } catch (err) {
        const { YMapDefaultFeaturesLayer } = ymaps3;
        if (YMapDefaultFeaturesLayer) {
          try {
            mapInstance.addChild(new YMapDefaultFeaturesLayer({}));
          } catch (_) {}
        }
        const toAdd = [];
        withCoords.forEach((point) => {
          const el = createMarkerElement(point, point.code === selectedCode, onSelectPoint);
          const marker = new YMapMarker({ coordinates: [point.lon, point.lat] }, el);
          mapInstance.addChild(marker);
          toAdd.push(marker);
        });
        clustererRef.current = toAdd.length ? { markers: toAdd, isLegacy: true } : null;
        return;
      }

      const features = withCoords.map((point, i) => ({
        type: 'Feature',
        id: point.code || `pvz-${i}`,
        geometry: { coordinates: [point.lon, point.lat] },
        properties: point,
      }));

      const marker = (feature) => {
        const point = feature.properties;
        const el = createMarkerElement(point, point.code === selectedCode, onSelectPoint);
        return new YMapMarker(
          { coordinates: feature.geometry.coordinates, source: CLUSTER_SOURCE_ID },
          el
        );
      };

      const cluster = (coordinates, clusterFeatures) => {
        const el = createClusterElement(clusterFeatures.length);
        return new YMapMarker(
          { coordinates, source: CLUSTER_SOURCE_ID },
          el
        );
      };

      const clusterer = new YMapClusterer({
        method: clusterByGrid({ gridSize: 80 }),
        features,
        marker,
        cluster,
      });

      mapInstance.addChild(clusterer);
      clustererRef.current = clusterer;
        }

        await initMap();
      } catch (err) {
        setMapError(err?.message || 'Ошибка отображения карты');
      }
    })();

    return () => {
      const cur = clustererRef.current;
      const mapInst = mapInstanceRef.current;
      if (mapInst && cur) {
        if (cur.isLegacy && cur.markers) {
          cur.markers.forEach((m) => {
            try {
              mapInst.removeChild(m);
            } catch (_) {}
          });
        } else if (!cur.isLegacy) {
          try {
            mapInst.removeChild(cur);
          } catch (_) {}
        }
        clustererRef.current = null;
      }
    };
  }, [mapCenter, points, selectedPoint, onSelectPoint]);

  if (loading) {
    return (
      <div className="cdek-map-page">
        <div className="cdek-map-page__loading">Загрузка карты…</div>
      </div>
    );
  }

  return (
    <div className="cdek-map-page">
      <div className="cdek-map-page__search-wrap">
        <div className="cdek-map-page__search">
          <input
            ref={searchInputRef}
            type="text"
            className="cdek-map-page__search-input"
            placeholder="Введите город для поиска ПВЗ"
            value={citySearch}
            onChange={(e) => setCitySearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                searchInputRef.current?.blur();
                handleCitySearch();
              }
            }}
          />
        </div>
      </div>
      <div className="cdek-map-page__container">
        <div ref={mapRef} className="cdek-map-page__map" />
        {mapError && (
          <div className="cdek-map-page__map-error" role="alert">
            <p className="cdek-map-page__map-error-text">{mapError}</p>
            <p className="cdek-map-page__map-error-hint">
              В кабинете Яндекс.Карт у ключа добавьте в «Разрешённые запросы»: <strong>https://miniapp.nixbi.ru/*</strong> и при необходимости <strong>https://*.telegram.org/*</strong>
            </p>
          </div>
        )}
      </div>

      {selectedPoint && (
        <div
          className="cdek-map-confirm-sheet"
          style={{
            paddingBottom: 'calc(16px + var(--tg-content-safe-area-inset-bottom, 0px) + var(--ios-safe-area-inset-bottom, 0px))',
          }}
        >
          <div className="cdek-map-confirm-sheet__row cdek-map-confirm-sheet__row--head">
            <span className="cdek-map-confirm-sheet__name">
              {selectedPoint.name || DELIVERY_TYPE_LABEL}
            </span>
            <button
              type="button"
              className="cdek-map-confirm-sheet__close"
              onClick={() => setSelectedPoint(null)}
              aria-label="Отменить выбор"
            >
              {CLOSE_ICON_SVG}
            </button>
          </div>
          <p className="cdek-map-confirm-sheet__address">{selectedPoint.address || '—'}</p>
          <div className="cdek-map-confirm-sheet__worktime-block">
            <span className="cdek-map-confirm-sheet__worktime-label">Время работы</span>
            <span className="cdek-map-confirm-sheet__worktime-text">
              {selectedPoint.work_time || '—'}
            </span>
          </div>
          <Button
            size="large"
            variant="primary"
            className="cdek-map-confirm-sheet__btn"
            onClick={confirmPickupPoint}
          >
            Доставить сюда
          </Button>
        </div>
      )}
    </div>
  );
}
