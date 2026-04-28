import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import './Orders.css';

/** FastAPI `detail` бывает строкой или массивом объектов `{ msg, type, loc, ... }` — в JSX объект нельзя. */
function formatApiErrorDetail(err: unknown, fallback: string): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (d == null || d === '') return fallback;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    const parts = d.map((item: unknown) => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg?: unknown }).msg);
      try {
        return JSON.stringify(item);
      } catch {
        return String(item);
      }
    });
    const s = parts.filter(Boolean).join('; ');
    return s || fallback;
  }
  if (typeof d === 'object' && d !== null && 'msg' in d) return String((d as { msg: unknown }).msg);
  try {
    return JSON.stringify(d);
  } catch {
    return String(d);
  }
}

interface Item {
  id: number;
  name: string;
  size: string[] | null;
  price: number; // Цена в юанях
  price_rub?: number; // Цена в рублях (рассчитанная)
  photos?: Array<{ file_path: string }>;
}

interface OrderItem {
  item_id?: number;
  name: string;
  size?: string;
  /** Китайское название (кастом и при необходимости отображение в заказе) */
  chinese_name?: string;
  quantity: number;
  price: number;
  link?: string;
  photo?: string;
  isCustom: boolean;
  estimated_weight_kg?: number;
  length_cm?: number;
  width_cm?: number;
  height_cm?: number;
}

interface AdminUserOption {
  id: number;
  tgid: number | null;
  firstname?: string | null;
  username?: string | null;
}

interface DeliveryMethod {
  id: number;
  code: string;
  name: string;
  required_fields: string[];
}

interface CdekPvzRow {
  code: string;
  name: string;
  address: string;
  address_short?: string;
  city_code?: number | null;
}

/** Ответ /delivery/pickup-points: массив или один объект; редко обёртка { items }. */
function unwrapPickupPointsResponse(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === 'object') {
    const o = data as Record<string, unknown>;
    if (Array.isArray(o.items)) return o.items;
    if (o.code != null || o.name != null || o.address != null) return [data];
  }
  return [];
}

function normalizeCdekPvzRow(raw: unknown): CdekPvzRow | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const code = o.code != null ? String(o.code).trim() : '';
  if (!code) return null;
  const name = o.name != null ? String(o.name) : '';
  const address = o.address != null ? String(o.address) : '';
  const address_short = o.address_short != null ? String(o.address_short) : undefined;
  const cc = o.city_code;
  let city_code: number | null | undefined;
  if (cc == null || cc === '') city_code = undefined;
  else if (typeof cc === 'number' && Number.isFinite(cc)) city_code = cc;
  else {
    const n = parseInt(String(cc), 10);
    city_code = Number.isFinite(n) ? n : undefined;
  }
  return { code, name, address, address_short, city_code };
}

const ManualOrderForm: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [orderLink, setOrderLink] = useState('');
  const [orderId, setOrderId] = useState<number | null>(null);

  // Данные формы
  const [items, setItems] = useState<OrderItem[]>([]);
  const [catalogSearchResults, setCatalogSearchResults] = useState<Item[]>([]);
  const [catalogSearchLoading, setCatalogSearchLoading] = useState(false);
  const [selectedCatalogItemObject, setSelectedCatalogItemObject] = useState<Item | null>(null);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isPaid, setIsPaid] = useState(false);

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [userOptions, setUserOptions] = useState<AdminUserOption[]>([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);

  // Состояния для добавления товаров
  const [showAddCatalogItem, setShowAddCatalogItem] = useState(false);
  const [showAddCustomItem, setShowAddCustomItem] = useState(false);
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<number | null>(null);
  const [selectedSize, setSelectedSize] = useState('');
  const [itemQuantity, setItemQuantity] = useState(1);
  const [customItemName, setCustomItemName] = useState('');
  const [customItemChineseName, setCustomItemChineseName] = useState('');
  const [customItemSize, setCustomItemSize] = useState('');
  const [customItemPrice, setCustomItemPrice] = useState('');
  const [customItemLink, setCustomItemLink] = useState('');
  const [customItemQuantity, setCustomItemQuantity] = useState(1);
  const [customItemPhotoPath, setCustomItemPhotoPath] = useState('');
  const [customPhotoUploading, setCustomPhotoUploading] = useState(false);
  const [customItemWeightKg, setCustomItemWeightKg] = useState('');
  const [customItemLengthCm, setCustomItemLengthCm] = useState('');
  const [customItemWidthCm, setCustomItemWidthCm] = useState('');
  const [customItemHeightCm, setCustomItemHeightCm] = useState('');
  const [itemSearchQuery, setItemSearchQuery] = useState('');
  const [showItemDropdown, setShowItemDropdown] = useState(false);

  const [deliveryMethods, setDeliveryMethods] = useState<DeliveryMethod[]>([]);
  const [deliveryMethodCode, setDeliveryMethodCode] = useState('');
  const [deliveryRecipientName, setDeliveryRecipientName] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [deliveryPostalCode, setDeliveryPostalCode] = useState('');
  const [deliveryCostOverride, setDeliveryCostOverride] = useState('');
  const [cdekCity, setCdekCity] = useState('');
  const [cdekCityCode, setCdekCityCode] = useState<number | null>(null);
  /** Результат последнего серверного поиска ПВЗ по address_query */
  const [cdekPvzSearchResults, setCdekPvzSearchResults] = useState<CdekPvzRow[]>([]);
  const [cdekCityConfirmLoading, setCdekCityConfirmLoading] = useState(false);
  const [cdekPvzSearchLoading, setCdekPvzSearchLoading] = useState(false);
  const [cdekPvzHasSearched, setCdekPvzHasSearched] = useState(false);
  const [cdekPvzFetchError, setCdekPvzFetchError] = useState('');
  const [cdekStreetQuery, setCdekStreetQuery] = useState('');
  const [cdekPointCode, setCdekPointCode] = useState('');
  const [showCdekPvzDropdown, setShowCdekPvzDropdown] = useState(false);
  const [cdekPreviewLoading, setCdekPreviewLoading] = useState(false);
  const [cdekPreviewError, setCdekPreviewError] = useState('');
  const [cdekPreviewCostRub, setCdekPreviewCostRub] = useState<number | null>(null);
  const [cdekPreviewTariff, setCdekPreviewTariff] = useState<number | null>(null);
  const [localPickupPoints, setLocalPickupPoints] = useState<Array<{ id: number; city: string; address: string }>>([]);
  const [localPickupPointId, setLocalPickupPointId] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiClient.get<DeliveryMethod[]>('/delivery/delivery-methods');
        setDeliveryMethods(Array.isArray(res.data) ? res.data : []);
      } catch {
        setDeliveryMethods([]);
      }
    })();
  }, []);

  useEffect(() => {
    if (deliveryMethodCode !== 'PICKUP_LOCAL') {
      setLocalPickupPoints([]);
      setLocalPickupPointId(null);
      return;
    }
    (async () => {
      try {
        const res = await apiClient.get<Array<{ id: number; city: string; address: string }>>(
          '/products/admin/delivery-local/local-pickup-points',
        );
        setLocalPickupPoints(Array.isArray(res.data) ? res.data : []);
      } catch {
        setLocalPickupPoints([]);
      }
    })();
  }, [deliveryMethodCode]);

  useEffect(() => {
    if (!showAddCatalogItem) return;
    const q = itemSearchQuery.trim();
    if (q.length < 1) {
      setCatalogSearchResults([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        setCatalogSearchLoading(true);
        const res = await apiClient.get<Item[]>('/products/admin/items', {
          params: { search: q, limit: 40 },
        });
        const raw = Array.isArray(res.data) ? res.data : [];
        const norm = raw.map((item: any) => ({
          ...item,
          price: typeof item.price === 'number' ? item.price : parseFloat(String(item.price || 0)),
          price_rub:
            typeof item.price_rub === 'number'
              ? item.price_rub
              : item.price_rub != null
                ? parseFloat(String(item.price_rub))
                : undefined,
        }));
        if (!cancelled) setCatalogSearchResults(norm);
      } catch {
        if (!cancelled) setCatalogSearchResults([]);
      } finally {
        if (!cancelled) setCatalogSearchLoading(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [showAddCatalogItem, itemSearchQuery]);

  // Закрытие выпадающего списка при клике вне его
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.item-search-container')) {
        setShowItemDropdown(false);
      }
      if (!target.closest('.user-search-container')) {
        setShowUserDropdown(false);
      }
      if (!target.closest('.cdek-pvz-search-container')) {
        setShowCdekPvzDropdown(false);
      }
    };

    if (showItemDropdown || showUserDropdown || showCdekPvzDropdown) {
      // click в фазе всплытия (не mousedown): иначе mousedown с кнопки «Поиск» закрывает только что открытый список ПВЗ
      document.addEventListener('click', handleClickOutside);
      return () => {
        document.removeEventListener('click', handleClickOutside);
      };
    }
  }, [showItemDropdown, showUserDropdown, showCdekPvzDropdown]);

  useEffect(() => {
    const q = userSearchQuery.trim();
    if (q.length < 1) {
      setUserOptions([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        setUserSearchLoading(true);
        const response = await apiClient.get<{ items: AdminUserOption[] }>(
          `/users/admin/users?q=${encodeURIComponent(q)}&skip=0&limit=20`,
        );
        if (!cancelled) {
          setUserOptions(response.data.items || []);
        }
      } catch {
        if (!cancelled) setUserOptions([]);
      } finally {
        if (!cancelled) setUserSearchLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [userSearchQuery]);

  /** Только проверка города и получение city_code (без загрузки всех ПВЗ). */
  const confirmCdekCity = async () => {
    setCdekPvzFetchError('');
    setCdekPreviewError('');
    setCdekPreviewCostRub(null);
    setCdekPreviewTariff(null);
    setCdekPvzSearchResults([]);
    setCdekPvzHasSearched(false);
    setShowCdekPvzDropdown(false);
    const city = cdekCity.trim();
    if (city.length < 2) {
      setCdekPvzFetchError('Введите название города (не короче 2 символов)');
      return;
    }
    setCdekCityConfirmLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('city', city);
      params.set('country_code', 'RU');
      params.set('limit', '1');
      const res = await apiClient.get<CdekPvzRow[]>(`/delivery/pickup-points?${params.toString()}`);
      const rawRows = unwrapPickupPointsResponse(res.data);
      const rows = rawRows.map(normalizeCdekPvzRow).filter((r): r is CdekPvzRow => r != null);
      if (rows.length === 0) {
        setCdekCityCode(null);
        setCdekPvzFetchError('Город не найден в справочнике СДЭК или нет ПВЗ');
        return;
      }
      const rawCc = rows[0]?.city_code;
      const cc = typeof rawCc === 'number' ? rawCc : rawCc != null ? parseInt(String(rawCc), 10) : NaN;
      if (!Number.isFinite(cc)) {
        setCdekCityCode(null);
        setCdekPvzFetchError('Не удалось определить код города СДЭК');
        return;
      }
      setCdekCityCode(cc);
      setCdekPointCode('');
      setCdekStreetQuery('');
      setDeliveryAddress('');
    } catch (e: any) {
      setCdekCityCode(null);
      setCdekPvzFetchError(formatApiErrorDetail(e, 'Не удалось проверить город'));
    } finally {
      setCdekCityConfirmLoading(false);
    }
  };

  /** Поиск ПВЗ на сервере по части адреса / названия (address_query). */
  const searchCdekPvzOnServer = async () => {
    setCdekPvzFetchError('');
    if (cdekCityCode == null) {
      setCdekPvzFetchError('Сначала подтвердите город кнопкой «Готово»');
      return;
    }
    const q = cdekStreetQuery.trim();
    if (q.length < 2) {
      setCdekPvzFetchError('Введите не меньше 2 символов для поиска ПВЗ');
      return;
    }
    setCdekPointCode('');
    setCdekPvzSearchLoading(true);
    setCdekPvzHasSearched(false);
    setShowCdekPvzDropdown(true);
    try {
      const params = new URLSearchParams();
      params.set('city_code', String(cdekCityCode));
      params.set('country_code', 'RU');
      params.set('address_query', q);
      params.set('limit', '80');
      const res = await apiClient.get<CdekPvzRow[]>(`/delivery/pickup-points?${params.toString()}`);
      const rawRows = unwrapPickupPointsResponse(res.data);
      const rows = rawRows.map(normalizeCdekPvzRow).filter((r): r is CdekPvzRow => r != null);
      setCdekPvzSearchResults(rows);
      setCdekPvzHasSearched(true);
      setShowCdekPvzDropdown(true);
    } catch (e: any) {
      setCdekPvzSearchResults([]);
      setCdekPvzHasSearched(true);
      setCdekPvzFetchError(formatApiErrorDetail(e, 'Не удалось выполнить поиск ПВЗ'));
      setShowCdekPvzDropdown(true);
    } finally {
      setCdekPvzSearchLoading(false);
    }
  };

  const handleCdekPreviewCost = async () => {
    setShowCdekPvzDropdown(false);
    setCdekPreviewError('');
    setCdekPreviewCostRub(null);
    setCdekPreviewTariff(null);
    if (items.length === 0) {
      setCdekPreviewError('Добавьте в заказ хотя бы один товар');
      return;
    }
    if (cdekCityCode == null || !cdekPointCode.trim()) {
      setCdekPreviewError('Сначала подтвердите город и выберите ПВЗ');
      return;
    }
    setCdekPreviewLoading(true);
    try {
      const previewItems = items.map(it => ({
        item_id: it.item_id ?? null,
        name: it.name,
        quantity: it.quantity,
        price: it.price,
        estimated_weight_kg: it.isCustom ? it.estimated_weight_kg ?? null : null,
        length_cm: it.isCustom ? it.length_cm ?? null : null,
        width_cm: it.isCustom ? it.width_cm ?? null : null,
        height_cm: it.isCustom ? it.height_cm ?? null : null,
      }));
      const { data } = await apiClient.post<{
        delivery_cost_rub?: number | null;
        cdek_tariff_code?: number | null;
      }>('/products/admin/orders/manual/preview-delivery-cost', {
        items: previewItems,
        delivery_method_code: 'CDEK',
        delivery_city_code: cdekCityCode,
        cdek_delivery_point_code: cdekPointCode.trim(),
      });
      if (data.delivery_cost_rub != null) {
        setCdekPreviewCostRub(Number(data.delivery_cost_rub));
      } else {
        setCdekPreviewError('Сервис не вернул стоимость доставки');
      }
      if (data.cdek_tariff_code != null) setCdekPreviewTariff(Number(data.cdek_tariff_code));
    } catch (e: any) {
      setCdekPreviewError(formatApiErrorDetail(e, 'Не удалось рассчитать доставку'));
    } finally {
      setCdekPreviewLoading(false);
    }
  };

  const handleAddCatalogItem = () => {
    if (!selectedCatalogItem) {
      setError('Выберите товар из каталога');
      return;
    }

    const catalogItem =
      selectedCatalogItemObject ?? catalogSearchResults.find(item => item.id === selectedCatalogItem);
    if (!catalogItem) {
      setError('Товар не найден — выберите позицию из списка поиска');
      return;
    }

    const sizes = catalogItem.size;
    if (sizes && sizes.length > 0 && !selectedSize) {
      setError('Выберите размер');
      return;
    }

    // Используем price_rub если есть, иначе рассчитываем (но это не должно произойти, т.к. бэкенд должен возвращать price_rub)
    const itemPriceRub = catalogItem.price_rub || Number(catalogItem.price) || 0;
    
    const newItem: OrderItem = {
      item_id: catalogItem.id,
      name: catalogItem.name,
      size: selectedSize || undefined,
      quantity: itemQuantity,
      price: itemPriceRub,  // Цена в рублях для заказа
      isCustom: false
    };

    setItems([...items, newItem]);
    setSelectedCatalogItem(null);
    setSelectedCatalogItemObject(null);
    setSelectedSize('');
    setItemQuantity(1);
    setItemSearchQuery('');
    setShowItemDropdown(false);
    setShowAddCatalogItem(false);
    setError('');
  };

  const handleAddCustomItem = () => {
    if (!customItemName.trim()) {
      setError('Введите название товара');
      return;
    }

    const price = parseFloat(customItemPrice);
    if (isNaN(price) || price <= 0) {
      setError('Введите корректную цену');
      return;
    }

    const w = parseFloat(String(customItemWeightKg).replace(',', '.'));
    const L = parseInt(customItemLengthCm, 10);
    const W = parseInt(customItemWidthCm, 10);
    const H = parseInt(customItemHeightCm, 10);
    if (!Number.isFinite(w) || w <= 0) {
      setError('Укажите вес отправления (кг за единицу), больше 0');
      return;
    }
    if (!Number.isFinite(L) || !Number.isFinite(W) || !Number.isFinite(H) || L < 1 || W < 1 || H < 1) {
      setError('Укажите длину, ширину и высоту в см (целые числа не меньше 1)');
      return;
    }

    const newItem: OrderItem = {
      name: customItemName.trim(),
      chinese_name: customItemChineseName.trim() || undefined,
      size: customItemSize.trim() || undefined,
      quantity: customItemQuantity,
      price: price,
      link: customItemLink.trim() || undefined,
      photo: customItemPhotoPath.trim() || undefined,
      isCustom: true,
      estimated_weight_kg: w,
      length_cm: L,
      width_cm: W,
      height_cm: H,
    };

    setItems([...items, newItem]);
    setCustomItemName('');
    setCustomItemChineseName('');
    setCustomItemSize('');
    setCustomItemPrice('');
    setCustomItemLink('');
    setCustomItemPhotoPath('');
    setCustomItemWeightKg('');
    setCustomItemLengthCm('');
    setCustomItemWidthCm('');
    setCustomItemHeightCm('');
    setCustomItemQuantity(1);
    setShowAddCustomItem(false);
    setError('');
  };

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (items.length === 0) {
      setError('Добавьте хотя бы один товар');
      return;
    }

    if (!phoneNumber.trim()) {
      setError('Введите номер телефона');
      return;
    }

    if (selectedUserId == null) {
      setError('Выберите пользователя из списка');
      return;
    }

    if (deliveryMethodCode) {
      if (!deliveryRecipientName.trim()) {
        setError('Укажите ФИО получателя для доставки');
        return;
      }
      if (deliveryMethodCode === 'PICKUP_LOCAL') {
        if (localPickupPointId == null || localPickupPointId <= 0) {
          setError('Выберите локальный пункт выдачи');
          return;
        }
      }
      if (deliveryMethodCode === 'COURIER_LOCAL' || deliveryMethodCode === 'CDEK_MANUAL') {
        if (!deliveryAddress.trim()) {
          setError('Укажите адрес доставки');
          return;
        }
      }
      if (deliveryMethodCode === 'CDEK') {
        if (!cdekCity.trim()) {
          setError('Укажите город (СДЭК)');
          return;
        }
        if (cdekCityCode == null) {
          setError('Для СДЭК нажмите «Готово» после ввода города и дождитесь загрузки списка ПВЗ');
          return;
        }
        if (!cdekPointCode.trim()) {
          setError('Выберите ПВЗ СДЭК из списка');
          return;
        }
      }
    }

    const deliveryPayload =
      deliveryMethodCode
        ? (() => {
            const d: Record<string, unknown> = {
              delivery_method_code: deliveryMethodCode,
              recipient_name: deliveryRecipientName.trim() || null,
            };
            const costRaw = deliveryCostOverride.trim().replace(',', '.');
            if (costRaw) {
              const c = parseFloat(costRaw);
              if (!Number.isNaN(c)) d.delivery_cost_rub = c;
            }
            if (deliveryMethodCode === 'PICKUP_LOCAL' && localPickupPointId != null && localPickupPointId > 0) {
              d.local_pickup_point_id = localPickupPointId;
            }
            if (deliveryMethodCode === 'COURIER_LOCAL' || deliveryMethodCode === 'CDEK_MANUAL') {
              d.address = deliveryAddress.trim() || null;
              d.postal_code = deliveryPostalCode.trim() || null;
            }
            if (deliveryMethodCode === 'CDEK') {
              d.delivery_city = cdekCity.trim() || null;
              d.cdek_delivery_point_code = cdekPointCode.trim() || null;
              d.address = deliveryAddress.trim() || null;
              d.postal_code = deliveryPostalCode.trim() || null;
              if (cdekCityCode != null) {
                d.delivery_city_code = cdekCityCode;
              }
            }
            return d;
          })()
        : undefined;

    try {
      setLoading(true);
      const response = await apiClient.post('/products/admin/orders/manual', {
        items: items.map(item => ({
          item_id: item.item_id || null,
          name: item.name,
          size: item.size || null,
          chinese_name: item.isCustom ? item.chinese_name?.trim() || null : null,
          quantity: item.quantity,
          price: item.price,
          link: item.link || null,
          photo: item.photo || null,
          ...(item.isCustom
            ? {
                estimated_weight_kg: item.estimated_weight_kg,
                length_cm: item.length_cm,
                width_cm: item.width_cm,
                height_cm: item.height_cm,
              }
            : {}),
        })),
        user_id: selectedUserId,
        phone_number: phoneNumber.trim(),
        is_paid: isPaid,
        ...(deliveryPayload ? { delivery: deliveryPayload } : {}),
      });

      setOrderId(response.data.id);
      setOrderLink(response.data.order_link);
      
      // Копируем ссылку в буфер обмена
      if (response.data.order_link) {
        try {
          await navigator.clipboard.writeText(response.data.order_link);
          setSuccess('Заказ успешно создан и привязан к пользователю. Ссылка на заказ скопирована в буфер обмена.');
        } catch (err) {
          setSuccess('Заказ успешно создан!');
        }
      } else {
        setSuccess('Заказ успешно создан!');
      }
      
      // Перенаправляем на страницу заказов через 2 секунды
      setTimeout(() => {
        navigate('/orders');
      }, 2000);
    } catch (err: any) {
      setError(formatApiErrorDetail(err, 'Ошибка создания заказа'));
      console.error('Ошибка создания заказа:', err);
    } finally {
      setLoading(false);
    }
  };

  const copyOrderLink = () => {
    if (orderLink) {
      navigator.clipboard.writeText(orderLink);
      setSuccess('Ссылка скопирована в буфер обмена!');
      setTimeout(() => setSuccess(''), 3000);
    }
  };

  const copyOrderId = () => {
    if (orderId) {
      const link = `https://t.me/${process.env.REACT_APP_TELEGRAM_BOT_USERNAME || ''}?startapp=order_${orderId}`;
      navigator.clipboard.writeText(link);
      setSuccess('Ссылка скопирована в буфер обмена!');
      setTimeout(() => setSuccess(''), 3000);
    }
  };

  const selectedCatalogItemData =
    selectedCatalogItemObject ??
    (selectedCatalogItem != null ? catalogSearchResults.find(item => item.id === selectedCatalogItem) : undefined);
  const availableSizes = selectedCatalogItemData?.size || [];

  const itemThumbSrc = (it: Item) => {
    const p = it.photos?.[0]?.file_path;
    if (!p) return '';
    return p.startsWith('/') ? p : `/${p}`;
  };

  const formatUserLabel = (u: AdminUserOption) => {
    const name = (u.firstname || '').trim();
    const un = u.username ? `@${u.username}` : '—';
    return `#${u.id} · TG ${u.tgid ?? '—'} · ${name || '—'} ${un}`;
  };

  const totalPrice = items.reduce((sum, item) => sum + (Number(item.price) * item.quantity), 0);

  return (
    <div className="manual-order-form">
      <div className="manual-order-header">
        <h1>Создание заказа вручную</h1>
        <button className="btn-secondary" onClick={() => navigate('/orders')}>
          ← Назад к заказам
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      {orderLink && (
        <div className="order-link-section">
          <h2>Заказ создан!</h2>
          <p>ID заказа: <span className="order-id-link" onClick={copyOrderId}>{orderId}</span></p>
          <div className="link-container">
            <input 
              type="text" 
              value={orderLink} 
              readOnly 
              className="link-input"
            />
            <button onClick={copyOrderLink} className="btn-primary">Копировать ссылку</button>
          </div>
          <p className="link-hint">Ссылка для открытия заказа в мини-приложении (заказ уже привязан к выбранному пользователю)</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="order-form">
        <div className="form-section">
          <h2>Товары в заказе</h2>
          
          {items.length > 0 && (
            <div className="items-list">
              {items.map((item, index) => (
                <div key={index} className="order-item-card">
                  <div className="item-info">
                    <h3>{item.name}</h3>
                    {item.chinese_name ? (
                      <p className="muted">Китайское название: {item.chinese_name}</p>
                    ) : null}
                    {item.size && <p>Размер: {item.size}</p>}
                    <p>Количество: {item.quantity}</p>
                    <p>Цена: {typeof item.price === 'number' ? item.price.toFixed(2) : parseFloat(String(item.price || 0)).toFixed(2)} ₽</p>
                    <p>Итого: {((typeof item.price === 'number' ? item.price : parseFloat(String(item.price || 0))) * item.quantity).toFixed(2)} ₽</p>
                    {item.link && <p><a href={item.link} target="_blank" rel="noopener noreferrer">Ссылка на товар</a></p>}
                    {item.isCustom &&
                      item.estimated_weight_kg != null &&
                      item.length_cm != null &&
                      item.width_cm != null &&
                      item.height_cm != null && (
                        <p className="muted">
                          Логистика: {item.estimated_weight_kg} кг / шт · {item.length_cm}×{item.width_cm}×
                          {item.height_cm} см
                        </p>
                      )}
                    {item.photo && (
                      <p>
                        <img
                          src={item.photo.startsWith('/') ? item.photo : `/${item.photo}`}
                          alt=""
                          style={{ maxWidth: 120, maxHeight: 120, objectFit: 'cover', borderRadius: 4 }}
                        />
                      </p>
                    )}
                  </div>
                  <button 
                    type="button" 
                    onClick={() => handleRemoveItem(index)}
                    className="btn-remove"
                  >
                    Удалить
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="total-price">
            <strong>Общая сумма: {totalPrice.toFixed(2)} ₽</strong>
          </div>

          <div className="add-item-buttons">
            <button 
              type="button" 
              onClick={() => {
                setShowAddCatalogItem(true);
                setShowAddCustomItem(false);
                setCatalogSearchResults([]);
                setSelectedCatalogItem(null);
                setSelectedCatalogItemObject(null);
                setItemSearchQuery('');
                setSelectedSize('');
              }}
              className="btn-primary"
            >
              + Добавить товар из каталога
            </button>
            <button 
              type="button" 
              onClick={() => {
                setShowAddCustomItem(true);
                setShowAddCatalogItem(false);
              }}
              className="btn-primary"
            >
              + Добавить кастомный товар
            </button>
          </div>

          {showAddCatalogItem && (
            <div className="add-item-modal">
              <h3>Добавить товар из каталога</h3>
              <div className="form-group">
                <label>Поиск товара:</label>
                <div className="item-search-container">
                  <input
                    type="text"
                    value={itemSearchQuery}
                    onChange={(e) => {
                      setItemSearchQuery(e.target.value);
                      setShowItemDropdown(true);
                      if (!e.target.value.trim()) {
                        setSelectedCatalogItem(null);
                        setSelectedCatalogItemObject(null);
                        setSelectedSize('');
                      }
                    }}
                    onFocus={() => setShowItemDropdown(true)}
                    placeholder="Введите название товара или ID..."
                    className="item-search-input"
                  />
                  {showItemDropdown && itemSearchQuery.trim() && catalogSearchLoading && (
                    <div className="item-search-dropdown">
                      <div className="item-search-no-results">Поиск на сервере…</div>
                    </div>
                  )}
                  {showItemDropdown &&
                    itemSearchQuery.trim() &&
                    !catalogSearchLoading &&
                    catalogSearchResults.length > 0 && (
                      <div className="item-search-dropdown">
                        {catalogSearchResults.map(item => (
                          <div
                            key={item.id}
                            className="item-search-result item-search-result-with-thumb"
                            onClick={() => {
                              setSelectedCatalogItem(item.id);
                              setSelectedCatalogItemObject(item);
                              setItemSearchQuery(item.name);
                              setShowItemDropdown(false);
                              setSelectedSize('');
                            }}
                          >
                            {itemThumbSrc(item) ? (
                              <img className="item-search-thumb" src={itemThumbSrc(item)} alt="" />
                            ) : (
                              <div className="item-search-thumb item-search-thumb-placeholder" aria-hidden />
                            )}
                            <div className="item-search-result-text">
                              <div className="item-search-name">{item.name}</div>
                              <div className="item-search-meta">#{item.id}</div>
                              <div className="item-search-price">
                                {item.price_rub
                                  ? (typeof item.price_rub === 'number'
                                      ? item.price_rub.toFixed(2)
                                      : parseFloat(String(item.price_rub || 0)).toFixed(2))
                                  : (typeof item.price === 'number'
                                      ? item.price.toFixed(2)
                                      : parseFloat(String(item.price || 0)).toFixed(2))}{' '}
                                ₽
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  {showItemDropdown &&
                    itemSearchQuery.trim() &&
                    !catalogSearchLoading &&
                    catalogSearchResults.length === 0 && (
                      <div className="item-search-dropdown">
                        <div className="item-search-no-results">Товары не найдены</div>
                      </div>
                    )}
                </div>
                {selectedCatalogItem && selectedCatalogItemData && (
                  <div className="selected-item-info">
                    <strong>Выбран: {selectedCatalogItemData.name}</strong>
                    <span className="selected-item-price">
                      {selectedCatalogItemData.price_rub
                        ? (typeof selectedCatalogItemData.price_rub === 'number' 
                            ? selectedCatalogItemData.price_rub.toFixed(2) 
                            : parseFloat(String(selectedCatalogItemData.price_rub || 0)).toFixed(2))
                        : (typeof selectedCatalogItemData.price === 'number' 
                            ? selectedCatalogItemData.price.toFixed(2) 
                            : parseFloat(String(selectedCatalogItemData.price || 0)).toFixed(2))} ₽
                    </span>
                  </div>
                )}
              </div>

              {selectedCatalogItemData && availableSizes.length > 0 && (
                <div className="form-group">
                  <label>Размер:</label>
                  <select 
                    value={selectedSize} 
                    onChange={(e) => setSelectedSize(e.target.value)}
                  >
                    <option value="">Выберите размер</option>
                    {availableSizes.map(size => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="form-group">
                <label>Количество:</label>
                <input 
                  type="number" 
                  min="1" 
                  value={itemQuantity} 
                  onChange={(e) => setItemQuantity(parseInt(e.target.value) || 1)}
                />
              </div>

              <div className="modal-buttons">
                <button type="button" onClick={handleAddCatalogItem} className="btn-primary">
                  Добавить
                </button>
                <button 
                  type="button" 
                  onClick={() => {
                    setShowAddCatalogItem(false);
                    setSelectedCatalogItem(null);
                    setSelectedCatalogItemObject(null);
                    setSelectedSize('');
                    setItemSearchQuery('');
                    setShowItemDropdown(false);
                  }}
                  className="btn-secondary"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}

          {showAddCustomItem && (
            <div className="add-item-modal">
              <h3>Добавить кастомный товар</h3>
              <div className="form-group">
                <label>Название товара:</label>
                <input 
                  type="text" 
                  value={customItemName} 
                  onChange={(e) => setCustomItemName(e.target.value)}
                  placeholder="Введите название"
                />
              </div>

              <div className="form-group">
                <label>Название на китайском (необязательно):</label>
                <input
                  type="text"
                  value={customItemChineseName}
                  onChange={e => setCustomItemChineseName(e.target.value)}
                  placeholder="中文名称"
                />
              </div>

              <div className="form-group">
                <label>Размер (необязательно):</label>
                <input
                  type="text"
                  value={customItemSize}
                  onChange={e => setCustomItemSize(e.target.value)}
                  placeholder="Например: M, 42, onesize"
                />
              </div>

              <div className="form-group">
                <label>Цена (₽):</label>
                <input 
                  type="number" 
                  step="0.01" 
                  min="0" 
                  value={customItemPrice} 
                  onChange={(e) => setCustomItemPrice(e.target.value)}
                  placeholder="0.00"
                />
              </div>

              <div className="form-group">
                <label>Вес одной единицы (кг) — для доставки и накладной</label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={customItemWeightKg}
                  onChange={(e) => setCustomItemWeightKg(e.target.value)}
                  placeholder="например 0.35"
                />
              </div>
              <div className="form-group">
                <label>Габариты одной единицы (см): длина × ширина × высота</label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    type="number"
                    min={1}
                    value={customItemLengthCm}
                    onChange={(e) => setCustomItemLengthCm(e.target.value)}
                    placeholder="Д"
                    style={{ width: 72 }}
                  />
                  <span>×</span>
                  <input
                    type="number"
                    min={1}
                    value={customItemWidthCm}
                    onChange={(e) => setCustomItemWidthCm(e.target.value)}
                    placeholder="Ш"
                    style={{ width: 72 }}
                  />
                  <span>×</span>
                  <input
                    type="number"
                    min={1}
                    value={customItemHeightCm}
                    onChange={(e) => setCustomItemHeightCm(e.target.value)}
                    placeholder="В"
                    style={{ width: 72 }}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Ссылка на товар (необязательно):</label>
                <input 
                  type="url" 
                  value={customItemLink} 
                  onChange={(e) => setCustomItemLink(e.target.value)}
                  placeholder="https://..."
                />
              </div>

              <div className="form-group">
                <label>Фото (необязательно, 1 шт.):</label>
                <input
                  type="file"
                  accept="image/*"
                  disabled={customPhotoUploading}
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setCustomPhotoUploading(true);
                    setError('');
                    try {
                      const fd = new FormData();
                      fd.append('photo', file);
                      const res = await apiClient.post<{ file_path: string }>(
                        '/products/admin/orders/manual/upload-custom-photo',
                        fd,
                      );
                      setCustomItemPhotoPath(res.data.file_path || '');
                    } catch (err: any) {
                      setError(formatApiErrorDetail(err, 'Не удалось загрузить фото'));
                    } finally {
                      setCustomPhotoUploading(false);
                      e.target.value = '';
                    }
                  }}
                />
                {customPhotoUploading && <p className="muted">Загрузка…</p>}
                {customItemPhotoPath && (
                  <p>
                    <img
                      src={`/${customItemPhotoPath}`}
                      alt=""
                      style={{ maxWidth: 160, maxHeight: 160, objectFit: 'cover', borderRadius: 4, marginTop: 8 }}
                    />
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ marginLeft: 8, verticalAlign: 'top' }}
                      onClick={() => setCustomItemPhotoPath('')}
                    >
                      Убрать фото
                    </button>
                  </p>
                )}
              </div>

              <div className="form-group">
                <label>Количество:</label>
                <input 
                  type="number" 
                  min="1" 
                  value={customItemQuantity} 
                  onChange={(e) => setCustomItemQuantity(parseInt(e.target.value) || 1)}
                />
              </div>

              <div className="modal-buttons">
                <button type="button" onClick={handleAddCustomItem} className="btn-primary">
                  Добавить
                </button>
                <button 
                  type="button" 
                  onClick={() => {
                    setShowAddCustomItem(false);
                    setCustomItemName('');
                    setCustomItemChineseName('');
                    setCustomItemSize('');
                    setCustomItemPrice('');
                    setCustomItemLink('');
                    setCustomItemPhotoPath('');
                    setCustomItemWeightKg('');
                    setCustomItemLengthCm('');
                    setCustomItemWidthCm('');
                    setCustomItemHeightCm('');
                  }}
                  className="btn-secondary"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="form-section">
          <h2>Клиент</h2>
          <div className="form-group">
            <label>Пользователь (поиск по id, TG id, @username, имени):</label>
            <div className="item-search-container user-search-container">
              <input
                type="text"
                value={userSearchQuery}
                onChange={(e) => {
                  setUserSearchQuery(e.target.value);
                  setShowUserDropdown(true);
                  if (!e.target.value.trim()) {
                    setSelectedUserId(null);
                  }
                }}
                onFocus={() => setShowUserDropdown(true)}
                placeholder="Начните ввод…"
                className="item-search-input"
              />
              {showUserDropdown && userSearchQuery.trim().length >= 1 && (
                <div className="item-search-dropdown">
                  {userSearchLoading && (
                    <div className="item-search-no-results">Поиск…</div>
                  )}
                  {!userSearchLoading && userOptions.length === 0 && (
                    <div className="item-search-no-results">Никого не найдено</div>
                  )}
                  {!userSearchLoading &&
                    userOptions.map((u) => (
                      <div
                        key={u.id}
                        className="item-search-result"
                        onClick={() => {
                          setSelectedUserId(u.id);
                          setUserSearchQuery(formatUserLabel(u));
                          setShowUserDropdown(false);
                        }}
                      >
                        <div className="item-search-name">{formatUserLabel(u)}</div>
                      </div>
                    ))}
                </div>
              )}
            </div>
            {selectedUserId != null && (
              <p className="muted">
                Выбран внутренний id: <strong>{selectedUserId}</strong>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ marginLeft: 12 }}
                  onClick={() => {
                    setSelectedUserId(null);
                    setUserSearchQuery('');
                  }}
                >
                  Сбросить
                </button>
              </p>
            )}
          </div>
        </div>

        <div className="form-section">
          <h2>Доставка (необязательно)</h2>
          <p className="muted">Без выбора способа заказ создаётся только с товарами и телефоном.</p>

          <div className="form-group">
            <label>Способ доставки</label>
            <select
              value={deliveryMethodCode}
              onChange={(e) => {
                setDeliveryMethodCode(e.target.value);
                setDeliveryAddress('');
                setDeliveryPostalCode('');
                setDeliveryCostOverride('');
                setCdekCity('');
                setCdekCityCode(null);
                setCdekPvzSearchResults([]);
                setCdekPvzHasSearched(false);
                setCdekPvzFetchError('');
                setCdekStreetQuery('');
                setCdekPointCode('');
                setShowCdekPvzDropdown(false);
                setCdekPreviewCostRub(null);
                setCdekPreviewTariff(null);
                setCdekPreviewError('');
                setLocalPickupPointId(null);
              }}
            >
              <option value="">— не указывать —</option>
              {deliveryMethods.map((m) => (
                <option key={m.id} value={m.code}>
                  {m.name} ({m.code})
                </option>
              ))}
            </select>
          </div>

          {deliveryMethodCode ? (
            <>
              <div className="form-group">
                <label>ФИО получателя</label>
                <input
                  type="text"
                  value={deliveryRecipientName}
                  onChange={(e) => setDeliveryRecipientName(e.target.value)}
                  placeholder="Как для доставки / накладной"
                />
              </div>
              <div className="form-group">
                <label>Стоимость доставки (₽), опционально</label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={deliveryCostOverride}
                  onChange={(e) => setDeliveryCostOverride(e.target.value)}
                  placeholder="Пусто — для СДЭК до ПВЗ посчитает сервер"
                />
              </div>

              {deliveryMethodCode === 'PICKUP_LOCAL' && (
                <div className="form-group">
                  <label>Локальный ПВЗ</label>
                  <select
                    value={localPickupPointId ?? ''}
                    onChange={(e) =>
                      setLocalPickupPointId(e.target.value ? parseInt(e.target.value, 10) : null)
                    }
                  >
                    <option value="">— выберите —</option>
                    {localPickupPoints.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.city}, {p.address}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {(deliveryMethodCode === 'COURIER_LOCAL' || deliveryMethodCode === 'CDEK_MANUAL') && (
                <>
                  <div className="form-group">
                    <label>Адрес</label>
                    <input
                      type="text"
                      value={deliveryAddress}
                      onChange={(e) => setDeliveryAddress(e.target.value)}
                      placeholder={
                        deliveryMethodCode === 'CDEK_MANUAL'
                          ? 'Полный адрес одной строкой'
                          : 'Улица, дом, квартира'
                      }
                    />
                  </div>
                  <div className="form-group">
                    <label>Индекс (необязательно)</label>
                    <input
                      type="text"
                      value={deliveryPostalCode}
                      onChange={(e) => setDeliveryPostalCode(e.target.value)}
                    />
                  </div>
                </>
              )}

              {deliveryMethodCode === 'CDEK' && (
                <>
                  <div className="form-group">
                    <label>Город получателя</label>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <input
                        type="text"
                        value={cdekCity}
                        onChange={(e) => {
                          setCdekCity(e.target.value);
                          setCdekCityCode(null);
                          setCdekPvzSearchResults([]);
                          setCdekPvzHasSearched(false);
                          setCdekPvzFetchError('');
                          setCdekPointCode('');
                          setCdekStreetQuery('');
                          setDeliveryAddress('');
                          setCdekPreviewCostRub(null);
                          setCdekPreviewTariff(null);
                          setCdekPreviewError('');
                        }}
                        placeholder="Например: Владивосток"
                        style={{ flex: '1 1 200px', minWidth: 160 }}
                      />
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={cdekCityConfirmLoading}
                        onClick={() => void confirmCdekCity()}
                      >
                        {cdekCityConfirmLoading ? 'Проверка…' : 'Готово'}
                      </button>
                    </div>
                    <p className="muted" style={{ marginTop: 6 }}>
                      Сначала подтвердите город. Затем введите улицу, дом или название ПВЗ и нажмите «Поиск» — список
                      придёт с сервера уже отфильтрованным.
                    </p>
                    {cdekPvzFetchError ? <div className="error-message" style={{ marginTop: 8 }}>{cdekPvzFetchError}</div> : null}
                    {cdekCityCode != null ? (
                      <p className="muted" style={{ marginTop: 6 }}>
                        Город подтверждён. Код города СДЭК: <strong>{cdekCityCode}</strong>
                      </p>
                    ) : null}
                  </div>
                  <div className="form-group cdek-pvz-search-container item-search-container">
                    <label>ПВЗ: поиск по адресу / названию</label>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <input
                        type="text"
                        value={cdekStreetQuery}
                        onChange={(e) => {
                          setCdekStreetQuery(e.target.value);
                          setCdekPvzSearchResults([]);
                          setCdekPvzHasSearched(false);
                          setShowCdekPvzDropdown(false);
                          setCdekPvzFetchError('');
                        }}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            void searchCdekPvzOnServer();
                          }
                        }}
                        disabled={cdekCityCode == null}
                        placeholder={
                          cdekCityCode == null
                            ? 'Сначала подтвердите город'
                            : 'Например: Ленина 15 или Океанский'
                        }
                        className="item-search-input"
                        style={{ flex: '1 1 200px', minWidth: 160 }}
                      />
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={
                          cdekCityCode == null ||
                          cdekStreetQuery.trim().length < 2 ||
                          cdekPvzSearchLoading
                        }
                        onClick={() => void searchCdekPvzOnServer()}
                      >
                        {cdekPvzSearchLoading ? 'Поиск…' : 'Поиск'}
                      </button>
                    </div>
                    {showCdekPvzDropdown &&
                      cdekCityCode != null &&
                      (cdekPvzSearchLoading || cdekPvzSearchResults.length > 0 || (cdekPvzHasSearched && !cdekPvzSearchLoading)) && (
                      <div className="item-search-dropdown" style={{ maxHeight: 280, overflowY: 'auto' }}>
                        {cdekPvzSearchLoading ? (
                          <div className="item-search-no-results">Запрос к серверу…</div>
                        ) : cdekPvzSearchResults.length === 0 ? (
                          <div className="item-search-no-results">Ничего не найдено — уточните запрос и нажмите «Поиск»</div>
                        ) : (
                          cdekPvzSearchResults.map(row => (
                            <div
                              key={row.code}
                              className="item-search-result"
                              onClick={() => {
                                setCdekPointCode(row.code);
                                setDeliveryAddress(row.address || row.address_short || row.name || '');
                                setShowCdekPvzDropdown(false);
                              }}
                            >
                              <div className="item-search-name">{row.address_short || row.address}</div>
                              <div className="item-search-price" style={{ fontSize: 12, opacity: 0.85 }}>
                                {row.code} · {row.name}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                  <div className="cdek-delivery-actions">
                    {cdekPointCode ? (
                      <p className="muted">
                        Выбран ПВЗ: <strong>{cdekPointCode}</strong>
                        {deliveryAddress ? ` — ${deliveryAddress}` : ''}
                      </p>
                    ) : null}
                    <div className="form-group">
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={
                          cdekPreviewLoading ||
                          items.length === 0 ||
                          cdekCityCode == null ||
                          !cdekPointCode.trim()
                        }
                        title={
                          items.length === 0
                            ? 'Добавьте в заказ хотя бы один товар'
                            : cdekCityCode == null
                              ? 'Сначала нажмите «Готово» и подтвердите город'
                              : !cdekPointCode.trim()
                                ? 'Выберите ПВЗ из списка после поиска'
                                : undefined
                        }
                        onClick={() => void handleCdekPreviewCost()}
                      >
                        {cdekPreviewLoading ? 'Расчёт…' : 'Рассчитать стоимость доставки'}
                      </button>
                      {cdekPreviewError ? (
                        <div className="error-message" style={{ marginTop: 8 }}>
                          {cdekPreviewError}
                        </div>
                      ) : null}
                      {cdekPreviewCostRub != null && !cdekPreviewError ? (
                        <p className="muted" style={{ marginTop: 8 }}>
                          Ориентир по текущему составу: <strong>{cdekPreviewCostRub.toFixed(2)} ₽</strong>
                          {cdekPreviewTariff != null ? ` (тариф СДЭК: ${cdekPreviewTariff})` : ''}. Тот же расчёт, что при
                          оформлении в миниаппе; итог в заказе может совпасть, если не задана ручная сумма доставки.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Индекс (необязательно)</label>
                    <input
                      type="text"
                      value={deliveryPostalCode}
                      onChange={(e) => setDeliveryPostalCode(e.target.value)}
                    />
                  </div>
                </>
              )}
            </>
          ) : null}
        </div>

        <div className="form-section">
          <h2>Контактные данные</h2>

          <div className="form-group">
            <label>Номер телефона:</label>
            <input 
              type="tel" 
              value={phoneNumber} 
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+7 (999) 123-45-67"
              required
            />
          </div>

          <div className="form-group">
            <label className="checkbox-label">
              <input 
                type="checkbox" 
                checked={isPaid} 
                onChange={(e) => setIsPaid(e.target.checked)}
              />
              <span>Заказ оплачен (бот пропустит стадию оплаты при привязке)</span>
            </label>
          </div>
        </div>

        <div className="form-actions">
          <button type="submit" disabled={loading} className="btn-primary btn-large">
            {loading ? 'Создание...' : 'Создать заказ'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ManualOrderForm;

