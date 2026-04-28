import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import { useAdminItemPricePreview } from '../../utils/useAdminItemPricePreview';
import AdminItemPricePreview from './AdminItemPricePreview';
import SizeChartCombo from './SizeChartCombo';
import './Catalog.css';

const GENDERS = [
  { value: 'М', label: 'Мужской' },
  { value: 'Ж', label: 'Женский' },
  { value: 'унисекс', label: 'Унисекс' }
];

interface ItemType {
  id: number;
  name: string;
}

interface SizeChartOption {
  id: number;
  name: string;
}

interface SizeChartGrid {
  rows: string[][];
}

interface BulkItem {
  name: string;
  chinese_name: string;
  description: string;
  link: string;
  photos: File[];
  photoPreviews: string[];
}

const BulkItemForm: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [itemTypes, setItemTypes] = useState<ItemType[]>([]);
  const [sizeCharts, setSizeCharts] = useState<SizeChartOption[]>([]);
  
  // Общие параметры
  const [commonPrice, setCommonPrice] = useState('');
  const [commonServiceFee, setCommonServiceFee] = useState('0');
  const [commonWeight, setCommonWeight] = useState('');
  const [commonLengthCm, setCommonLengthCm] = useState('');
  const [commonWidthCm, setCommonWidthCm] = useState('');
  const [commonHeightCm, setCommonHeightCm] = useState('');
  const [commonItemTypeId, setCommonItemTypeId] = useState('');
  const [commonGender, setCommonGender] = useState('');
  const [commonSizeChartId, setCommonSizeChartId] = useState<number | '' | 'new'>('');
  const [newSizeChart, setNewSizeChart] = useState<{ name: string; grid: SizeChartGrid }>({
    name: '',
    grid: { rows: [['']] }
  });
  const [newSizeChartLoading, setNewSizeChartLoading] = useState(false);
  const [sizes, setSizes] = useState<string[]>(['']);
  const [tags, setTags] = useState<string[]>(['']);
  const [isNumericRange, setIsNumericRange] = useState(false);
  const [numericRange, setNumericRange] = useState({ from: '', to: '' });

  // Группа и режим массового добавления
  const [groupName, setGroupName] = useState('');
  const [mode, setMode] = useState<'different' | 'one_for_all'>('different');
  const [commonName, setCommonName] = useState('');
  const [commonLink, setCommonLink] = useState('');
  const [commonDescription, setCommonDescription] = useState('');
  
  // Массив товаров
  const [items, setItems] = useState<BulkItem[]>([
    { name: '', chinese_name: '', description: '', link: '', photos: [], photoPreviews: [] }
  ]);

  const bulkPricePreview = useAdminItemPricePreview({
    price: commonPrice,
    service_fee_percent: commonServiceFee,
    estimated_weight_kg: commonWeight,
  });

  useEffect(() => {
    fetchItemTypes();
    fetchSizeCharts();
  }, []);

  const fetchItemTypes = async () => {
    try {
      const response = await apiClient.get('/products/admin/item-types');
      setItemTypes(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки типов товаров:', err);
    }
  };

  const fetchSizeCharts = async () => {
    try {
      const response = await apiClient.get('/products/admin/size-charts');
      setSizeCharts(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки таблиц размеров:', err);
    }
  };

  const sizeChartGridSetCell = (rowIndex: number, colIndex: number, value: string) => {
    setNewSizeChart(prev => {
      const rows = prev.grid.rows.map((r, ri) =>
        ri === rowIndex ? r.map((c, ci) => (ci === colIndex ? value : c)) : r
      );
      return { ...prev, grid: { rows } };
    });
  };
  const sizeChartGridAddRow = () => {
    setNewSizeChart(prev => {
      const colCount = prev.grid.rows[0]?.length || 1;
      return { ...prev, grid: { rows: [...prev.grid.rows, Array(colCount).fill('')] } };
    });
  };
  const sizeChartGridAddCol = () => {
    setNewSizeChart(prev => ({
      ...prev,
      grid: { rows: prev.grid.rows.map(row => [...row, '']) }
    }));
  };
  const sizeChartGridRemoveRow = (rowIndex: number) => {
    if (newSizeChart.grid.rows.length <= 1) return;
    setNewSizeChart(prev => ({
      ...prev,
      grid: { rows: prev.grid.rows.filter((_, i) => i !== rowIndex) }
    }));
  };
  const sizeChartGridRemoveCol = (colIndex: number) => {
    const colCount = newSizeChart.grid.rows[0]?.length ?? 0;
    if (colCount <= 1) return;
    setNewSizeChart(prev => ({
      ...prev,
      grid: { rows: prev.grid.rows.map(row => row.filter((_, i) => i !== colIndex)) }
    }));
  };
  const createSizeChartAndSelect = async () => {
    if (!newSizeChart.name.trim()) {
      setError('Введите название размерной сетки');
      return;
    }
    setNewSizeChartLoading(true);
    setError('');
    try {
      const res = await apiClient.post('/products/admin/size-charts', {
        name: newSizeChart.name.trim(),
        grid: newSizeChart.grid
      });
      setSizeCharts(prev => [...prev, { id: res.data.id, name: res.data.name }]);
      setCommonSizeChartId(res.data.id);
      setNewSizeChart({ name: '', grid: { rows: [['']] } });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания размерной сетки');
    } finally {
      setNewSizeChartLoading(false);
    }
  };
  const cancelNewSizeChart = () => {
    setCommonSizeChartId('');
    setNewSizeChart({ name: '', grid: { rows: [['']] } });
  };

  const handleSizeChange = (index: number, value: string) => {
    const newSizes = [...sizes];
    newSizes[index] = value;
    setSizes(newSizes);
  };

  const handleAddSize = () => {
    setSizes([...sizes, '']);
  };

  const handleRemoveSize = (index: number) => {
    if (sizes.length > 1) {
      const newSizes = sizes.filter((_, i) => i !== index);
      setSizes(newSizes);
    } else {
      setSizes(['']);
    }
  };

  const handleTagChange = (index: number, value: string) => {
    const newTags = [...tags];
    newTags[index] = value;
    setTags(newTags);
  };
  const handleAddTag = () => setTags([...tags, '']);
  const handleRemoveTag = (index: number) => {
    if (tags.length > 1) {
      setTags(tags.filter((_, i) => i !== index));
    } else {
      setTags(['']);
    }
  };

  const handleNumericRangeApply = () => {
    const from = parseInt(numericRange.from);
    const to = parseInt(numericRange.to);
    
    if (isNaN(from) || isNaN(to) || from > to) {
      setError('Неверный диапазон. Укажите корректные числа, где первое число меньше или равно второму.');
      return;
    }
    
    const rangeSizes: string[] = [];
    for (let i = from; i <= to; i++) {
      rangeSizes.push(String(i));
    }
    setSizes(rangeSizes);
    setIsNumericRange(false);
    setNumericRange({ from: '', to: '' });
  };

  const handleItemChange = (index: number, field: keyof BulkItem, value: string) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const handleItemPhotoChange = (itemIndex: number, files: FileList | null) => {
    if (!files) return;
    
    const newItems = [...items];
    const newPhotos: File[] = [];
    const newPreviews: string[] = [];
    const fileArray = Array.from(files).filter(file => file.type.startsWith('image/'));
    
    if (fileArray.length === 0) return;
    
    let loadedCount = 0;
    fileArray.forEach((file, idx) => {
      newPhotos.push(file);
      const reader = new FileReader();
      reader.onload = (e) => {
        if (e.target?.result) {
          newPreviews.push(e.target.result as string);
          loadedCount++;
          if (loadedCount === fileArray.length) {
            newItems[itemIndex] = {
              ...newItems[itemIndex],
              photos: [...newItems[itemIndex].photos, ...newPhotos],
              photoPreviews: [...newItems[itemIndex].photoPreviews, ...newPreviews]
            };
            setItems(newItems);
          }
        }
      };
      reader.readAsDataURL(file);
    });
  };

  const readFileAsDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        if (e.target?.result) resolve(e.target.result as string);
        else reject(new Error('Не удалось прочитать файл'));
      };
      reader.onerror = () => reject(new Error('Не удалось прочитать файл'));
      reader.readAsDataURL(file);
    });

  const handleSplitPhotosToItems = async (files: FileList | null) => {
    if (!files) return;
    const fileArray = Array.from(files).filter((file) => file.type.startsWith('image/'));
    if (fileArray.length === 0) return;
    try {
      const previews = await Promise.all(fileArray.map((file) => readFileAsDataUrl(file)));
      const rows: BulkItem[] = fileArray.map((file, i) => ({
        name: '',
        chinese_name: '',
        description: '',
        link: '',
        photos: [file],
        photoPreviews: [previews[i]],
      }));
      setItems((prev) => [...prev, ...rows]);
    } catch (err) {
      console.error('Ошибка подготовки фото для разбиения по товарам:', err);
      setError('Не удалось обработать загруженные фото');
    }
  };

  const handleRemoveItemPhoto = (itemIndex: number, photoIndex: number) => {
    const newItems = [...items];
    newItems[itemIndex].photos.splice(photoIndex, 1);
    newItems[itemIndex].photoPreviews.splice(photoIndex, 1);
    setItems(newItems);
  };

  const handleAddItem = () => {
    setItems([...items, { name: '', chinese_name: '', description: '', link: '', photos: [], photoPreviews: [] }]);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length > 1) {
      setItems(items.filter((_, i) => i !== index));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Валидация общих параметров
    if (!commonPrice || !commonItemTypeId || !commonGender) {
      setError('Заполните все обязательные общие параметры (цена, тип товара, пол)');
      return;
    }

    // Валидация товаров в зависимости от режима
    const isOneForAll = mode === 'one_for_all';
    if (isOneForAll && !commonName.trim()) {
      setError('В режиме «Один товар на все» укажите общее название товара');
      return;
    }
    const validItems = isOneForAll
      ? items
      : items.filter(item => item.name.trim() !== '');
    if (validItems.length === 0) {
      setError(isOneForAll ? 'Добавьте хотя бы одну позицию (с фото или без)' : 'Добавьте хотя бы один товар с названием');
      return;
    }

    // Проверка наличия фото
    const itemsWithoutPhotos = validItems.filter(item => item.photos.length === 0);
    if (itemsWithoutPhotos.length > 0) {
      if (!window.confirm('Некоторые товары не имеют фото. Продолжить создание?')) {
        return;
      }
    }

    try {
      setLoading(true);

      // Подготовка данных
      const validSizes = sizes.filter(s => s.trim() !== '');
      const validTags = tags.filter(t => t.trim() !== '');
      const requestData: Record<string, unknown> = {
        price: parseFloat(commonPrice),
        service_fee_percent: parseFloat(commonServiceFee) || 0,
        estimated_weight_kg: commonWeight ? parseFloat(commonWeight) : null,
        length_cm: commonLengthCm ? parseInt(commonLengthCm, 10) : null,
        width_cm: commonWidthCm ? parseInt(commonWidthCm, 10) : null,
        height_cm: commonHeightCm ? parseInt(commonHeightCm, 10) : null,
        item_type_id: parseInt(commonItemTypeId),
        gender: commonGender,
        size_chart_id: (commonSizeChartId !== '' && commonSizeChartId !== 'new') ? (commonSizeChartId as number) : null,
        size: validSizes.length > 0 ? validSizes.map(s => s.trim()) : null,
        tags: validTags.length > 0 ? validTags.map(t => t.trim()) : null,
        group_name: groupName.trim() || undefined,
        items: validItems.map((item, itemIndex) => {
          // Вычисляем индексы фото в общем массиве
          // Используем validItems для правильного подсчета индексов
          let photoStartIndex = 0;
          for (let i = 0; i < itemIndex; i++) {
            photoStartIndex += validItems[i].photos.length;
          }
          const photoIndices: number[] = [];
          for (let i = 0; i < item.photos.length; i++) {
            photoIndices.push(photoStartIndex + i);
          }
          
          // В режиме «один на все» имя/ссылка/описание уходят в common_*
          if (isOneForAll) {
            return {
              name: '',
              chinese_name: item.chinese_name.trim() || null,
              description: null,
              link: null,
              photo_indices: photoIndices.length > 0 ? photoIndices : null
            };
          }
          // Валидация и обработка link для режима «разные товары»
          let linkValue: string | null = null;
          if (item.link && item.link.trim()) {
            const trimmedLink = item.link.trim();
            if (trimmedLink.startsWith('http://') || trimmedLink.startsWith('https://')) {
              linkValue = trimmedLink.length > 500 ? trimmedLink.substring(0, 500) : trimmedLink;
            } else if (trimmedLink.length > 200) {
              console.warn(`Подозрительно длинная ссылка для товара "${item.name}": ${trimmedLink.substring(0, 100)}...`);
              linkValue = null;
            } else {
              linkValue = trimmedLink;
            }
          }
          return {
            name: item.name.trim(),
            chinese_name: item.chinese_name.trim() || null,
            description: item.description.trim() || null,
            link: linkValue,
            photo_indices: photoIndices.length > 0 ? photoIndices : null
          };
        })
      };
      if (isOneForAll) {
        requestData.common_name = commonName.trim();
        requestData.common_link = commonLink.trim() || null;
        requestData.common_description = commonDescription.trim() || null;
      }

      // Собираем все фото в один массив
      const allPhotos: File[] = [];
      validItems.forEach(item => {
        allPhotos.push(...item.photos);
      });

      // Читаем файлы в Blob-снимки, чтобы избежать ERR_UPLOAD_FILE_CHANGED
      // (облачные папки, антивирус и т.д. могут менять файл во время загрузки)
      const photoBlobs: { blob: Blob; filename: string }[] = [];
      for (const photo of allPhotos) {
        const buffer = await photo.arrayBuffer();
        const blob = new Blob([buffer], { type: photo.type || 'image/jpeg' });
        photoBlobs.push({ blob, filename: photo.name || 'photo.jpg' });
      }

      // Создаем FormData
      const formData = new FormData();
      formData.append('request_data', JSON.stringify(requestData));
      
      // Добавляем фото как Blob-снимки (имя поля 'photos' для всех)
      photoBlobs.forEach(({ blob, filename }) => {
        formData.append('photos', blob, filename);
      });

      // Логируем данные для отладки
      console.log('Отправка данных:', {
        requestData,
        photosCount: allPhotos.length,
        itemsCount: validItems.length
      });

      // Отправляем запрос (не указываем Content-Type - браузер установит автоматически с boundary)
      const response = await apiClient.post('/products/admin/items/bulk-create', formData);

      const createdItems = response.data;
      alert(`Успешно создано товаров: ${createdItems.length}`);
      navigate('/catalog');
    } catch (err: any) {
      console.error('Ошибка создания товаров:', err);
      
      // Обработка ошибок валидации
      if (err.response?.status === 422) {
        const detail = err.response?.data?.detail;
        if (Array.isArray(detail)) {
          // Ошибки валидации Pydantic
          const errorMessages = detail.map((e: any) => {
            const field = e.loc?.join('.') || 'unknown';
            return `${field}: ${e.msg}`;
          }).join('\n');
          setError(`Ошибки валидации:\n${errorMessages}`);
        } else if (typeof detail === 'string') {
          setError(detail);
        } else {
          setError('Ошибка валидации данных. Проверьте правильность заполнения формы.');
        }
      } else {
        setError(err.response?.data?.detail || err.message || 'Ошибка создания товаров');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="catalog-page">
      <div className="catalog-header">
        <h1>Массовое добавление товаров</h1>
        <button onClick={() => navigate('/catalog')} className="btn-secondary">
          ← Назад к каталогу
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <form onSubmit={handleSubmit} className="item-form">
        {/* Группа и режим */}
        <div className="form-section">
          <h2>Группа и режим</h2>
          <div className="form-group">
            <label>Название группы</label>
            <input
              type="text"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="Все созданные товары попадут в эту группу (необязательно)"
            />
          </div>
          <div className="form-group">
            <label>Режим добавления</label>
            <div className="bulk-mode-options">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="bulk-mode"
                  checked={mode === 'different'}
                  onChange={() => setMode('different')}
                />
                Разные товары (у каждого своё название и ссылка)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="bulk-mode"
                  checked={mode === 'one_for_all'}
                  onChange={() => setMode('one_for_all')}
                />
                Один товар на все позиции (одно название и ссылка)
              </label>
            </div>
          </div>
          {mode === 'one_for_all' && (
            <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid var(--border-medium, #d4d4d4)', borderRadius: '8px', background: 'var(--bg-secondary, #fafafa)' }}>
              <div className="form-group">
                <label>Общее название товара *</label>
                <input
                  type="text"
                  value={commonName}
                  onChange={(e) => setCommonName(e.target.value)}
                  placeholder="Название для всех позиций"
                />
              </div>
              <div className="form-group">
                <label>Общая ссылка</label>
                <input
                  type="url"
                  value={commonLink}
                  onChange={(e) => setCommonLink(e.target.value)}
                  placeholder="https://..."
                />
              </div>
              <div className="form-group">
                <label>Общее описание</label>
                <textarea
                  value={commonDescription}
                  onChange={(e) => setCommonDescription(e.target.value)}
                  placeholder="Описание для всех позиций"
                  rows={3}
                />
              </div>
              <div className="form-group">
                <label>Пакетная загрузка фото (1 фото = 1 позиция/товар)</label>
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={(e) => {
                    void handleSplitPhotosToItems(e.target.files);
                    e.currentTarget.value = '';
                  }}
                />
                <small>Например, 40 фото за раз создадут 40 позиций с одним фото в каждой.</small>
              </div>
            </div>
          )}
        </div>

        {/* Общие параметры */}
        <div className="form-section">
          <h2>Общие параметры (для всех товаров)</h2>
          
          <div className="form-group">
            <label>Тип товара *</label>
            <select
              value={commonItemTypeId}
              onChange={(e) => setCommonItemTypeId(e.target.value)}
              required
            >
              <option value="">Выберите тип</option>
              {itemTypes.map(type => (
                <option key={type.id} value={type.id}>{type.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Пол *</label>
            <select
              value={commonGender}
              onChange={(e) => setCommonGender(e.target.value)}
              required
            >
              <option value="">Выберите пол</option>
              {GENDERS.map(g => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Цена (¥) *</label>
            <input
              type="number"
              step="0.01"
              value={commonPrice}
              onChange={(e) => setCommonPrice(e.target.value)}
              required
            />
          </div>

          <div className="form-group form-group--service-fee-preview">
            <label>Наценка / сервисный сбор (%)</label>
            <div className="item-service-fee-row">
              <div className="item-service-fee-row__input">
                <input
                  type="number"
                  step="0.01"
                  value={commonServiceFee}
                  onChange={(e) => setCommonServiceFee(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <AdminItemPricePreview
                preview={bulkPricePreview.preview}
                loading={bulkPricePreview.loading}
                idleMessage={
                  commonPrice.trim() === ''
                    ? 'Укажите цену в ¥ — появится расчёт цены для клиента и ориентировочного дохода.'
                    : undefined
                }
              />
            </div>
            <small>Те же расчёты, что для одного товара: курс, доставка за кг при указанном весе, эквайринг.</small>
          </div>

          <div className="form-group">
            <label>Вес (кг)</label>
            <input
              type="number"
              step="0.01"
              value={commonWeight}
              onChange={(e) => setCommonWeight(e.target.value)}
            />
          </div>

          <div className="form-group form-dimensions-row">
            <div>
              <label>Длина (см)</label>
              <input
                type="number"
                min={0}
                value={commonLengthCm}
                onChange={(e) => setCommonLengthCm(e.target.value)}
              />
            </div>
            <div>
              <label>Ширина (см)</label>
              <input
                type="number"
                min={0}
                value={commonWidthCm}
                onChange={(e) => setCommonWidthCm(e.target.value)}
              />
            </div>
            <div>
              <label>Высота (см)</label>
              <input
                type="number"
                min={0}
                value={commonHeightCm}
                onChange={(e) => setCommonHeightCm(e.target.value)}
              />
            </div>
            <small className="form-dimensions-row__hint">Габариты посылки (обувь ~40×30×15, шмотки ~40×30×10)</small>
          </div>

          <div className="form-group">
            <label>Таблица размеров</label>
            <SizeChartCombo
              value={commonSizeChartId === 'new' ? 'new' : commonSizeChartId === '' ? '' : String(commonSizeChartId)}
              onChange={(v) => {
                if (v === '') setCommonSizeChartId('');
                else if (v === 'new') setCommonSizeChartId('new');
                else setCommonSizeChartId(parseInt(v, 10));
              }}
              options={sizeCharts}
              noneLabel="— Не задана —"
              createNewLabel="➕ Создать новую таблицу"
              placeholder="Поиск по названию или выберите из списка…"
            />
            {commonSizeChartId === 'new' && (
              <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid var(--border-medium, #d4d4d4)', borderRadius: '8px', background: 'var(--bg-secondary, #fafafa)' }}>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.25rem' }}>Название сетки</label>
                  <input
                    type="text"
                    value={newSizeChart.name}
                    onChange={(e) => setNewSizeChart(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Например: Обувь Nike"
                    style={{ width: '100%', maxWidth: '300px' }}
                  />
                </div>
                <div style={{ marginBottom: '0.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type="button" onClick={sizeChartGridAddRow} className="btn-secondary" style={{ padding: '0.35rem 0.75rem' }}>+ Строка</button>
                  <button type="button" onClick={sizeChartGridAddCol} className="btn-secondary" style={{ padding: '0.35rem 0.75rem' }}>+ Столбец</button>
                </div>
                <div className="size-chart-editor-scroll" style={{ marginBottom: '0.75rem' }}>
                  <table style={{ borderCollapse: 'collapse', minWidth: '200px' }}>
                    <tbody>
                      {newSizeChart.grid.rows.map((row, ri) => (
                        <tr key={ri}>
                          {row.map((cell, ci) => (
                            <td key={ci} style={{ padding: '2px' }}>
                              <input
                                type="text"
                                value={cell}
                                onChange={(e) => sizeChartGridSetCell(ri, ci, e.target.value)}
                                style={{ width: '70px', padding: '4px' }}
                              />
                            </td>
                          ))}
                          <td style={{ padding: '2px' }}>
                            <button type="button" onClick={() => sizeChartGridRemoveRow(ri)} className="btn-delete" style={{ padding: '0.25rem 0.5rem' }} title="Удалить строку">−</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {newSizeChart.grid.rows[0] && newSizeChart.grid.rows[0].length > 1 && (
                    <div style={{ marginTop: '4px' }}>
                      Удалить столбец:{' '}
                      {newSizeChart.grid.rows[0].map((_, ci) => (
                        <button key={ci} type="button" onClick={() => sizeChartGridRemoveCol(ci)} className="btn-delete" style={{ padding: '0.2rem 0.4rem', marginRight: '4px' }}>{ci + 1}</button>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type="button" onClick={createSizeChartAndSelect} disabled={newSizeChartLoading} className="btn-primary" style={{ padding: '0.5rem 1rem' }}>
                    {newSizeChartLoading ? 'Создание...' : 'Создать и выбрать'}
                  </button>
                  <button type="button" onClick={cancelNewSizeChart} className="btn-secondary" style={{ padding: '0.5rem 1rem' }}>
                    Отмена
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Размеры</label>
            <div className="sizes-container">
              <div className="sizes-inputs">
                {sizes.map((size, index) => (
                  <div key={index} className="size-input-group">
                    <input
                      type="text"
                      value={size}
                      onChange={(e) => handleSizeChange(index, e.target.value)}
                      placeholder="Размер"
                    />
                    {sizes.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveSize(index)}
                        className="btn-remove"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <div className="sizes-actions">
                <button type="button" onClick={handleAddSize} className="btn-add">
                  + Добавить размер
                </button>
                <button
                  type="button"
                  onClick={() => setIsNumericRange(!isNumericRange)}
                  className="btn-secondary"
                >
                  {isNumericRange ? 'Отменить' : 'Числовые размеры (диапазон)'}
                </button>
              </div>
              {isNumericRange && (
                <div className="numeric-range">
                  <input
                    type="number"
                    placeholder="От"
                    value={numericRange.from}
                    onChange={(e) => setNumericRange({ ...numericRange, from: e.target.value })}
                  />
                  <input
                    type="number"
                    placeholder="До"
                    value={numericRange.to}
                    onChange={(e) => setNumericRange({ ...numericRange, to: e.target.value })}
                  />
                  <button type="button" onClick={handleNumericRangeApply} className="btn-primary">
                    Применить
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>Теги (общие для всех товаров)</label>
            <div className="sizes-container">
              <div className="sizes-inputs">
                {tags.map((tag, index) => (
                  <div key={index} className="size-input-group">
                    <input
                      type="text"
                      value={tag}
                      onChange={(e) => handleTagChange(index, e.target.value)}
                      placeholder="Тег"
                    />
                    {tags.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveTag(index)}
                        className="btn-remove"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <div className="sizes-actions">
                <button type="button" onClick={handleAddTag} className="btn-add">
                  + Добавить тег
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Товары */}
        <div className="form-section">
          <h2>{mode === 'one_for_all' ? 'Позиции (фото для каждой)' : 'Товары'}</h2>
          
          {items.map((item, itemIndex) => (
            <div key={itemIndex} className="bulk-item-card">
              <div className="bulk-item-header">
                <h3>{mode === 'one_for_all' ? `Позиция ${itemIndex + 1}` : `Товар ${itemIndex + 1}`}</h3>
                {items.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveItem(itemIndex)}
                    className="btn-delete"
                  >
                    {mode === 'one_for_all' ? 'Удалить позицию' : 'Удалить товар'}
                  </button>
                )}
              </div>

              {mode === 'different' && (
                <>
                  <div className="form-group">
                    <label>Название *</label>
                    <input
                      type="text"
                      value={item.name}
                      onChange={(e) => handleItemChange(itemIndex, 'name', e.target.value)}
                      placeholder="Название товара"
                    />
                  </div>
                  <div className="form-group">
                    <label>Название на китайском</label>
                    <input
                      type="text"
                      value={item.chinese_name}
                      onChange={(e) => handleItemChange(itemIndex, 'chinese_name', e.target.value)}
                      placeholder="Опционально"
                    />
                  </div>

                  <div className="form-group">
                    <label>Описание</label>
                    <textarea
                      value={item.description}
                      onChange={(e) => handleItemChange(itemIndex, 'description', e.target.value)}
                      placeholder="Описание товара"
                      rows={3}
                    />
                  </div>

                  <div className="form-group">
                    <label>Ссылка</label>
                    <input
                      type="url"
                      value={item.link}
                      onChange={(e) => handleItemChange(itemIndex, 'link', e.target.value)}
                      placeholder="https://..."
                    />
                  </div>
                </>
              )}

              {mode === 'one_for_all' && (
                <div className="form-group">
                  <label>Название на китайском (для этой позиции)</label>
                  <input
                    type="text"
                    value={item.chinese_name}
                    onChange={(e) => handleItemChange(itemIndex, 'chinese_name', e.target.value)}
                    placeholder="Опционально"
                  />
                </div>
              )}

              <div className="form-group">
                <label>Фото</label>
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={(e) => handleItemPhotoChange(itemIndex, e.target.files)}
                />
                {item.photoPreviews.length > 0 && (
                  <div className="photo-previews">
                    {item.photoPreviews.map((preview, photoIndex) => (
                      <div key={photoIndex} className="photo-preview">
                        <img src={preview} alt={`Preview ${photoIndex + 1}`} />
                        <button
                          type="button"
                          onClick={() => handleRemoveItemPhoto(itemIndex, photoIndex)}
                          className="btn-remove"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          <button type="button" onClick={handleAddItem} className="btn-add">
            + {mode === 'one_for_all' ? 'Добавить позицию' : 'Добавить товар'}
          </button>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Создание...' : 'Создать товары'}
          </button>
          <button type="button" onClick={() => navigate('/catalog')} className="btn-secondary">
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
};

export default BulkItemForm;
