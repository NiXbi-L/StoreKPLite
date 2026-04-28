import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../../utils/apiClient';
import SizeChartCombo from './SizeChartCombo';
import './Catalog.css';

// Типы товаров будут загружаться из API

const GENDERS = [
  { value: 'М', label: 'Мужской' },
  { value: 'Ж', label: 'Женский' },
  { value: 'унисекс', label: 'Унисекс' }
];

interface ItemType {
  id: number;
  name: string;
}

interface ItemFormData {
  name: string;
  chinese_name: string;
  description: string;
  price: string;
  service_fee_percent: string;
  estimated_weight_kg: string;
  length_cm: string;
  width_cm: string;
  height_cm: string;
  item_type_id: string;
  gender: string;
  link: string;
  size_chart_id: string; // '' | number (as string) | 'new'
  is_legit: boolean;
  fixed_price: string;
}

interface SizeChartListItem {
  id: number;
  name: string;
}

interface SizeChartGrid {
  rows: string[][];
}

interface ItemPhoto {
  id: number;
  file_path: string;
  telegram_file_id: string | null;
  vk_attachment: string | null;
  sort_order?: number;
}

const ItemForm: React.FC = () => {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const isEdit = !!itemId;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState<ItemFormData>({
    name: '',
    chinese_name: '',
    description: '',
    price: '',
    service_fee_percent: '0',
    estimated_weight_kg: '',
    length_cm: '',
    width_cm: '',
    height_cm: '',
    item_type_id: '',
    gender: '',
    link: '',
    size_chart_id: '',
    is_legit: false,
    fixed_price: ''
  });
  const [sizes, setSizes] = useState<string[]>(['']);
  const [tags, setTags] = useState<string[]>(['']);
  const [isNumericRange, setIsNumericRange] = useState(false);
  const [numericRange, setNumericRange] = useState({ from: '', to: '' });
  const [photos, setPhotos] = useState<ItemPhoto[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedFilePreviews, setSelectedFilePreviews] = useState<Array<{file: File, preview: string}>>([]);
  const [itemTypes, setItemTypes] = useState<ItemType[]>([]);
  const [sizeChartsList, setSizeChartsList] = useState<SizeChartListItem[]>([]);
  const [newSizeChart, setNewSizeChart] = useState<{ name: string; grid: SizeChartGrid }>({
    name: '',
    grid: { rows: [['']] }
  });
  const [editingSizeChartId, setEditingSizeChartId] = useState<number | null>(null);
  const [sizeChartEditLoading, setSizeChartEditLoading] = useState(false);

  useEffect(() => {
    fetchItemTypes();
    fetchSizeCharts();
    if (isEdit && itemId) {
      fetchItem(parseInt(itemId));
    }
  }, [itemId, isEdit]);

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
      setSizeChartsList(response.data || []);
    } catch (err: any) {
      console.error('Ошибка загрузки размерных сеток:', err);
    }
  };

  const fetchItem = async (id: number) => {
    try {
      setLoading(true);
      const response = await apiClient.get(`/products/admin/items/${id}`);
      const item = response.data;
      setFormData({
        name: item.name || '',
        chinese_name: item.chinese_name || '',
        description: item.description || '',
        price: String(item.price || ''),
        service_fee_percent: String(item.service_fee_percent || '0'),
        estimated_weight_kg: item.estimated_weight_kg ? String(item.estimated_weight_kg) : '',
        length_cm: item.length_cm != null ? String(item.length_cm) : '',
        width_cm: item.width_cm != null ? String(item.width_cm) : '',
        height_cm: item.height_cm != null ? String(item.height_cm) : '',
        item_type_id: item.item_type_id ? String(item.item_type_id) : '',
        gender: item.gender || '',
        link: item.link || '',
        size_chart_id: item.size_chart_id != null ? String(item.size_chart_id) : '',
        is_legit: Boolean(item.is_legit),
        fixed_price: item.fixed_price != null ? String(item.fixed_price) : ''
      });
      
      // Обработка размеров: может быть массив или null
      if (item.size && Array.isArray(item.size) && item.size.length > 0) {
        setSizes(item.size);
      } else {
        setSizes(['']);
      }
      if (item.tags && Array.isArray(item.tags) && item.tags.length > 0) {
        setTags(item.tags);
      } else {
        setTags(['']);
      }
      
      // Сортируем фото по sort_order
      const photosList = item.photos || [];
      const sortedPhotos = photosList.sort((a: ItemPhoto, b: ItemPhoto) => {
        const aOrder = a.sort_order !== undefined ? a.sort_order : a.id;
        const bOrder = b.sort_order !== undefined ? b.sort_order : b.id;
        return aOrder - bOrder;
      });
      setPhotos(sortedPhotos);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки товара');
      console.error('Ошибка загрузки товара:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: keyof ItemFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleCheckboxChange = (field: keyof ItemFormData, value: boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }));
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
    try {
      const res = await apiClient.post('/products/admin/size-charts', {
        name: newSizeChart.name.trim(),
        grid: newSizeChart.grid
      });
      setSizeChartsList(prev => [...prev, { id: res.data.id, name: res.data.name }]);
      setFormData(prev => ({ ...prev, size_chart_id: String(res.data.id) }));
      setNewSizeChart({ name: '', grid: { rows: [['']] } });
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания размерной сетки');
    }
  };

  const startEditSizeChart = async () => {
    const id = formData.size_chart_id ? parseInt(formData.size_chart_id, 10) : 0;
    if (!id || isNaN(id)) return;
    setSizeChartEditLoading(true);
    setError('');
    try {
      const res = await apiClient.get(`/products/admin/size-charts/${id}`);
      const chart = res.data;
      const rows = chart?.grid?.rows ?? [];
      setNewSizeChart({
        name: chart?.name ?? '',
        grid: { rows: rows.length > 0 ? rows : [['']] }
      });
      setEditingSizeChartId(id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки размерной сетки');
    } finally {
      setSizeChartEditLoading(false);
    }
  };

  const saveSizeChartEdit = async () => {
    if (editingSizeChartId == null) return;
    if (!newSizeChart.name.trim()) {
      setError('Введите название размерной сетки');
      return;
    }
    setSizeChartEditLoading(true);
    setError('');
    try {
      await apiClient.patch(`/products/admin/size-charts/${editingSizeChartId}`, {
        name: newSizeChart.name.trim(),
        grid: newSizeChart.grid
      });
      setSizeChartsList(prev =>
        prev.map(c => (c.id === editingSizeChartId ? { ...c, name: newSizeChart.name.trim() } : c))
      );
      setEditingSizeChartId(null);
      setNewSizeChart({ name: '', grid: { rows: [['']] } });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка сохранения размерной сетки');
    } finally {
      setSizeChartEditLoading(false);
    }
  };

  const cancelSizeChartEdit = () => {
    setEditingSizeChartId(null);
    setNewSizeChart({ name: '', grid: { rows: [['']] } });
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
    setError('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      if (photos.length + selectedFiles.length + files.length > 10) {
        setError('Максимум 10 фотографий на товар');
        return;
      }
      
      // Создаем превью для выбранных файлов
      const newFiles = [...selectedFiles, ...files];
      const newPreviews = [...selectedFilePreviews];
      
      files.forEach((file) => {
        const preview = URL.createObjectURL(file);
        newPreviews.push({ file, preview });
      });
      
      setSelectedFiles(newFiles);
      setSelectedFilePreviews(newPreviews);
      
      // Сбрасываем input, чтобы можно было выбрать те же файлы снова
      e.target.value = '';
    }
  };

  const handleMoveFileUp = (index: number) => {
    if (index === 0) return;
    const newFiles = [...selectedFiles];
    const newPreviews = [...selectedFilePreviews];
    
    [newFiles[index], newFiles[index - 1]] = [newFiles[index - 1], newFiles[index]];
    [newPreviews[index], newPreviews[index - 1]] = [newPreviews[index - 1], newPreviews[index]];
    
    setSelectedFiles(newFiles);
    setSelectedFilePreviews(newPreviews);
  };

  const handleMoveFileDown = (index: number) => {
    if (index === selectedFiles.length - 1) return;
    const newFiles = [...selectedFiles];
    const newPreviews = [...selectedFilePreviews];
    
    [newFiles[index], newFiles[index + 1]] = [newFiles[index + 1], newFiles[index]];
    [newPreviews[index], newPreviews[index + 1]] = [newPreviews[index + 1], newPreviews[index]];
    
    setSelectedFiles(newFiles);
    setSelectedFilePreviews(newPreviews);
  };

  const handleRemoveSelectedFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    const previewToRevoke = selectedFilePreviews[index].preview;
    URL.revokeObjectURL(previewToRevoke);
    const newPreviews = selectedFilePreviews.filter((_, i) => i !== index);
    
    setSelectedFiles(newFiles);
    setSelectedFilePreviews(newPreviews);
  };

  const handleMovePhotoUp = async (index: number) => {
    if (index === 0) return;
    const newPhotos = [...photos];
    [newPhotos[index], newPhotos[index - 1]] = [newPhotos[index - 1], newPhotos[index]];
    setPhotos(newPhotos);
    
    // Обновляем порядок на сервере
    try {
      const photoIds = newPhotos.map(p => p.id);
      await apiClient.post(`/products/admin/items/${itemId}/photos/reorder`, { photo_ids: photoIds });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка изменения порядка фотографий');
      // Откатываем изменения
      setPhotos(photos);
    }
  };

  const handleMovePhotoDown = async (index: number) => {
    if (index === photos.length - 1) return;
    const newPhotos = [...photos];
    [newPhotos[index], newPhotos[index + 1]] = [newPhotos[index + 1], newPhotos[index]];
    setPhotos(newPhotos);
    
    // Обновляем порядок на сервере
    try {
      const photoIds = newPhotos.map(p => p.id);
      await apiClient.post(`/products/admin/items/${itemId}/photos/reorder`, { photo_ids: photoIds });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка изменения порядка фотографий');
      // Откатываем изменения
      setPhotos(photos);
    }
  };

  const handleDeletePhoto = async (photoId: number) => {
    if (!window.confirm('Удалить эту фотографию?')) {
      return;
    }

    try {
      await apiClient.delete(`/products/admin/items/photos/${photoId}`);
      setPhotos(photos.filter(p => p.id !== photoId));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления фотографии');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Проверяем наличие фотографий
    if (!isEdit && selectedFiles.length === 0) {
      setError('Пожалуйста, выберите хотя бы одну фотографию');
      return;
    }
    
    if (isEdit && photos.length === 0 && selectedFiles.length === 0) {
      setError('У товара должна быть хотя бы одна фотография');
      return;
    }

    try {
      setLoading(true);
      const payload: any = {
        name: formData.name.trim(),
        chinese_name: formData.chinese_name.trim() === '' ? null : formData.chinese_name.trim(),
        price: parseFloat(formData.price),
        service_fee_percent: 0,
        item_type_id: parseInt(formData.item_type_id),
        gender: formData.gender,
        is_legit: formData.is_legit,
        fixed_price: parseFloat(formData.price),
      };
      
      // Обработка опциональных полей - пустые строки преобразуем в null
      // ВАЖНО: Всегда отправляем эти поля, даже если они пустые (как null),
      // чтобы бэкенд знал, что поле было передано и нужно его обновить
      const descriptionTrimmed = formData.description.trim();
      payload.description = descriptionTrimmed === '' ? null : descriptionTrimmed;
      
      // Обработка размеров: фильтруем пустые значения и отправляем массив или null
      const validSizes = sizes.filter(s => s.trim() !== '');
      payload.size = validSizes.length > 0 ? validSizes.map(s => s.trim()) : null;
      const validTags = tags.filter(t => t.trim() !== '');
      payload.tags = validTags.length > 0 ? validTags.map(t => t.trim()) : null;
      
      const linkTrimmed = formData.link.trim();
      payload.link = linkTrimmed === '' ? null : linkTrimmed;
      
      const estimatedWeightStr = formData.estimated_weight_kg.trim();
      payload.estimated_weight_kg = estimatedWeightStr === '' ? null : parseFloat(estimatedWeightStr);

      let sizeChartIdToUse: number | null = null;
      if (formData.size_chart_id === 'new' && newSizeChart.name.trim()) {
        const createRes = await apiClient.post('/products/admin/size-charts', {
          name: newSizeChart.name.trim(),
          grid: newSizeChart.grid
        });
        sizeChartIdToUse = createRes.data.id;
      } else if (formData.size_chart_id && formData.size_chart_id !== 'new') {
        sizeChartIdToUse = parseInt(formData.size_chart_id, 10);
      }
      payload.size_chart_id = sizeChartIdToUse;

      const lengthStr = formData.length_cm.trim();
      payload.length_cm = lengthStr === '' ? null : parseInt(lengthStr, 10);
      const widthStr = formData.width_cm.trim();
      payload.width_cm = widthStr === '' ? null : parseInt(widthStr, 10);
      const heightStr = formData.height_cm.trim();
      payload.height_cm = heightStr === '' ? null : parseInt(heightStr, 10);

      let item;
      if (isEdit && itemId) {
        // Обновление
        const response = await apiClient.put(`/products/admin/items/${itemId}`, payload);
        item = response.data;
      } else {
        // Создание
        const response = await apiClient.post('/products/admin/items', payload);
        item = response.data;
      }

      // Загружаем фотографии в порядке, установленном пользователем
      const uploadedPhotoIds: number[] = [];
      if (selectedFiles.length > 0) {
        for (const file of selectedFiles) {
          const formDataPhotos = new FormData();
          formDataPhotos.append('photo', file);
          const photoResponse = await apiClient.post(`/products/admin/items/${item.id}/photos`, formDataPhotos, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });
          uploadedPhotoIds.push(photoResponse.data.id);
        }
        
        // Обновляем порядок загруженных фотографий согласно порядку выбранных файлов
        // Порядок загруженных фото соответствует порядку selectedFiles
        if (uploadedPhotoIds.length > 0) {
          // Получаем все фотографии товара (включая только что загруженные)
          const itemResponse = await apiClient.get(`/products/admin/items/${item.id}`);
          const updatedItem = itemResponse.data;
          const allPhotos = [...(updatedItem.photos || [])];
          
          // Сортируем существующие фото по sort_order, затем добавляем новые в конце
          const existingPhotos = allPhotos.filter(p => !uploadedPhotoIds.includes(p.id));
          const newPhotos = allPhotos.filter(p => uploadedPhotoIds.includes(p.id));
          
          // Сортируем существующие фото
          existingPhotos.sort((a, b) => {
            const aOrder = a.sort_order !== undefined ? a.sort_order : a.id;
            const bOrder = b.sort_order !== undefined ? b.sort_order : b.id;
            return aOrder - bOrder;
          });
          
          // Новые фото добавляем в конце, но сохраняем порядок из selectedFiles
          // uploadedPhotoIds содержит ID в порядке загрузки (который соответствует порядку selectedFiles)
          const orderedNewPhotos = uploadedPhotoIds
            .map(id => newPhotos.find(p => p.id === id))
            .filter((p): p is ItemPhoto => p !== undefined);
          
          // Объединяем существующие и новые фото в правильном порядке
          const finalOrder = [...existingPhotos, ...orderedNewPhotos].map(p => p.id);
          
          // Обновляем порядок всех фотографий на сервере
          if (finalOrder.length > 0) {
            await apiClient.post(`/products/admin/items/${item.id}/photos/reorder`, { photo_ids: finalOrder });
          }
        }
      }

      // Очищаем превью
      selectedFilePreviews.forEach(({ preview }) => {
        URL.revokeObjectURL(preview);
      });
      setSelectedFiles([]);
      setSelectedFilePreviews([]);

      navigate(`/catalog/${item.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка сохранения товара');
      console.error('Ошибка сохранения:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading && isEdit && !formData.name) {
    return <div className="catalog-page">Загрузка...</div>;
  }

  return (
    <div className="catalog-page">
      <div className="item-form-header">
        <h1>{isEdit ? 'Редактирование товара' : 'Создание товара'}</h1>
        <button onClick={() => navigate('/catalog')} className="btn-secondary">
          Отмена
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <form onSubmit={handleSubmit} className="item-form">
        <div className="form-group">
          <label>Название *</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleInputChange('name', e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Название на китайском</label>
          <input
            type="text"
            value={formData.chinese_name}
            onChange={(e) => handleInputChange('chinese_name', e.target.value)}
            placeholder="Опционально"
          />
        </div>

        <div className="form-group">
          <label>Описание</label>
          <textarea
            value={formData.description}
            onChange={(e) => handleInputChange('description', e.target.value)}
            rows={4}
          />
        </div>

        <div className="form-group">
          <label>Фиксированная цена (₽) *</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={formData.price}
            onChange={(e) => handleInputChange('price', e.target.value)}
            required
          />
          <small>Единая цена товара в рублях без формул и перерасчётов.</small>
        </div>

        <div className="form-group">
          <label>Ориентировочный вес (кг)</label>
          <input
            type="number"
            step="0.01"
            value={formData.estimated_weight_kg}
            onChange={(e) => handleInputChange('estimated_weight_kg', e.target.value)}
            min="0"
          />
          <small>Вес посылки для расчета стоимости доставки</small>
        </div>

        <div className="form-group form-dimensions-row">
          <div>
            <label>Длина (см)</label>
            <input
              type="number"
              min="0"
              value={formData.length_cm}
              onChange={(e) => handleInputChange('length_cm', e.target.value)}
            />
          </div>
          <div>
            <label>Ширина (см)</label>
            <input
              type="number"
              min="0"
              value={formData.width_cm}
              onChange={(e) => handleInputChange('width_cm', e.target.value)}
            />
          </div>
          <div>
            <label>Высота (см)</label>
            <input
              type="number"
              min="0"
              value={formData.height_cm}
              onChange={(e) => handleInputChange('height_cm', e.target.value)}
            />
          </div>
          <small className="form-dimensions-row__hint">Габариты посылки для СДЭК (объёмный вес). Обувь ~40×30×15, шмотки ~40×30×10</small>
        </div>

        <div className="form-group">
          <label>Тип вещи *</label>
          <select
            value={formData.item_type_id}
            onChange={(e) => handleInputChange('item_type_id', e.target.value)}
            required
          >
            <option value="">-- Выберите --</option>
            {itemTypes.map(type => (
              <option key={type.id} value={type.id}>{type.name}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Пол *</label>
          <select
            value={formData.gender}
            onChange={(e) => handleInputChange('gender', e.target.value)}
            required
          >
            <option value="">-- Выберите --</option>
            {GENDERS.map(g => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={formData.is_legit}
              onChange={(e) => handleCheckboxChange('is_legit', e.target.checked)}
              style={{ marginRight: '0.5rem' }}
            />
            Оригинал (легит)
          </label>
          <small>Отметьте, если товар является оригиналом. Если выключено — считается репликой.</small>
        </div>

        <div className="form-group">
          <label>Размеры</label>
          
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', marginBottom: '0.5rem' }}>
              <input
                type="checkbox"
                checked={isNumericRange}
                onChange={(e) => {
                  setIsNumericRange(e.target.checked);
                  if (!e.target.checked) {
                    setNumericRange({ from: '', to: '' });
                  }
                }}
              />
              <span>Числовые размеры (диапазон)</span>
            </label>
            
            {isNumericRange ? (
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                <input
                  type="number"
                  placeholder="От"
                  value={numericRange.from}
                  onChange={(e) => setNumericRange({ ...numericRange, from: e.target.value })}
                  style={{ width: '100px' }}
                />
                <span>-</span>
                <input
                  type="number"
                  placeholder="До"
                  value={numericRange.to}
                  onChange={(e) => setNumericRange({ ...numericRange, to: e.target.value })}
                  style={{ width: '100px' }}
                />
                <button
                  type="button"
                  onClick={handleNumericRangeApply}
                  className="btn-primary"
                  style={{ padding: '0.5rem 1rem' }}
                >
                  Применить
                </button>
              </div>
            ) : (
              <div style={{ marginBottom: '0.5rem' }}>
                {sizes.map((size, index) => (
                  <div key={index} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      value={size}
                      onChange={(e) => handleSizeChange(index, e.target.value)}
                      placeholder="Например: S, M, L, XL или 42"
                      style={{ flex: 1 }}
                    />
                    {sizes.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveSize(index)}
                        className="btn-delete"
                        style={{ padding: '0.5rem 1rem' }}
                      >
                        Удалить
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={handleAddSize}
                  className="btn-secondary"
                  style={{ padding: '0.5rem 1rem', marginTop: '0.5rem' }}
                >
                  + Добавить размер
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="form-group">
          <label>Теги (для поиска)</label>
          <div style={{ marginBottom: '0.5rem' }}>
            {tags.map((tag, index) => (
              <div key={index} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <input
                  type="text"
                  value={tag}
                  onChange={(e) => handleTagChange(index, e.target.value)}
                  placeholder="Например: Nike, кроссовки"
                  style={{ flex: 1 }}
                />
                {tags.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(index)}
                    className="btn-delete"
                    style={{ padding: '0.5rem 1rem' }}
                  >
                    Удалить
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={handleAddTag}
              className="btn-secondary"
              style={{ padding: '0.5rem 1rem', marginTop: '0.5rem' }}
            >
              + Добавить тег
            </button>
          </div>
        </div>

        <div className="form-group">
          <label>Ссылка</label>
          <input
            type="text"
            value={formData.link}
            onChange={(e) => handleInputChange('link', e.target.value)}
            placeholder="https://example.com/item"
          />
        </div>

        <div className="form-group">
          <label>Размерная сетка</label>
          <SizeChartCombo
            value={formData.size_chart_id}
            onChange={(v) => handleInputChange('size_chart_id', v)}
            options={sizeChartsList}
            disabled={editingSizeChartId != null}
            noneLabel="— Без размерной сетки —"
            createNewLabel="➕ Создать новую таблицу"
            placeholder="Поиск по названию или выберите из списка…"
          />
          {formData.size_chart_id && formData.size_chart_id !== 'new' && editingSizeChartId == null && (
            <button
              type="button"
              onClick={startEditSizeChart}
              disabled={sizeChartEditLoading}
              className="btn-secondary"
              style={{ marginTop: '0.5rem', padding: '0.5rem 1rem' }}
            >
              {sizeChartEditLoading ? 'Загрузка...' : 'Редактировать выбранную сетку'}
            </button>
          )}
          {(formData.size_chart_id === 'new' || editingSizeChartId != null) && (
            <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid var(--border-medium, #d4d4d4)', borderRadius: '8px', background: 'var(--bg-secondary, #fafafa)' }}>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ display: 'block', marginBottom: '0.25rem' }}>
                  {editingSizeChartId != null ? 'Редактирование сетки' : 'Название сетки'}
                </label>
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
                {editingSizeChartId != null ? (
                  <>
                    <button type="button" onClick={saveSizeChartEdit} disabled={sizeChartEditLoading} className="btn-primary" style={{ padding: '0.5rem 1rem' }}>
                      {sizeChartEditLoading ? 'Сохранение...' : 'Сохранить изменения'}
                    </button>
                    <button type="button" onClick={cancelSizeChartEdit} className="btn-secondary" style={{ padding: '0.5rem 1rem' }}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={createSizeChartAndSelect} className="btn-primary" style={{ padding: '0.5rem 1rem' }}>
                    Создать сетку и выбрать
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {isEdit && photos.length > 0 && (
          <div className="form-group">
            <label>Текущие фотографии ({photos.length}/10)</label>
            <div className="photos-grid">
              {photos.map((photo, index) => (
                <div key={photo.id} className="photo-item" style={{ position: 'relative' }}>
                  <div style={{ position: 'absolute', top: '5px', right: '5px', display: 'flex', gap: '5px', zIndex: 10 }}>
                    <button
                      type="button"
                      onClick={() => handleMovePhotoUp(index)}
                      disabled={index === 0}
                      className="btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: index === 0 ? 0.5 : 1 }}
                      title="Переместить вверх"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleMovePhotoDown(index)}
                      disabled={index === photos.length - 1}
                      className="btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: index === photos.length - 1 ? 0.5 : 1 }}
                      title="Переместить вниз"
                    >
                      ↓
                    </button>
                  </div>
                  <div style={{ position: 'absolute', bottom: '5px', left: '5px', background: 'rgba(0,0,0,0.7)', color: 'white', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                    #{index + 1}
                  </div>
                  <img
                    src={`/${photo.file_path}`}
                    alt="Фото"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="150" height="150"%3E%3Crect width="150" height="150" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3EОшибка%3C/text%3E%3C/svg%3E';
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => handleDeletePhoto(photo.id)}
                    className="btn-delete"
                    style={{ marginTop: '0.5rem' }}
                  >
                    Удалить
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="form-group">
          <label>
            {isEdit ? 'Добавить фотографии' : 'Фотографии (до 10 штук) *'}
          </label>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={handleFileChange}
            disabled={photos.length + selectedFiles.length >= 10}
          />
          <small>
            {isEdit
              ? `Можно выбрать несколько файлов. Уже загружено: ${photos.length}. Можно добавить еще: ${Math.max(0, 10 - photos.length - selectedFiles.length)}.`
              : `Можно выбрать несколько файлов (Ctrl+Click или Cmd+Click). Максимум 10 фотографий. Выбрано: ${selectedFiles.length}.`}
          </small>
          
          {selectedFilePreviews.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                Выбранные файлы (порядок загрузки можно изменить):
              </label>
              <div className="photos-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '1rem' }}>
                {selectedFilePreviews.map((item, index) => (
                  <div key={index} className="photo-item" style={{ position: 'relative', border: '2px dashed #ddd', borderRadius: '8px', padding: '0.5rem' }}>
                    <div style={{ position: 'absolute', top: '5px', right: '5px', display: 'flex', gap: '5px', zIndex: 10 }}>
                      <button
                        type="button"
                        onClick={() => handleMoveFileUp(index)}
                        disabled={index === 0}
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: index === 0 ? 0.5 : 1 }}
                        title="Переместить вверх"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => handleMoveFileDown(index)}
                        disabled={index === selectedFilePreviews.length - 1}
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: index === selectedFilePreviews.length - 1 ? 0.5 : 1 }}
                        title="Переместить вниз"
                      >
                        ↓
                      </button>
                    </div>
                    <div style={{ position: 'absolute', bottom: '5px', left: '5px', background: 'rgba(0,0,0,0.7)', color: 'white', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem' }}>
                      #{index + 1}
                    </div>
                    <img
                      src={item.preview}
                      alt={`Preview ${index + 1}`}
                      style={{ width: '100%', height: '150px', objectFit: 'cover', borderRadius: '4px' }}
                      onLoad={() => {}}
                    />
                    <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#666', wordBreak: 'break-all' }}>
                      {item.file.name}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveSelectedFile(index)}
                      className="btn-delete"
                      style={{ marginTop: '0.5rem', width: '100%', padding: '0.5rem' }}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Сохранение...' : (isEdit ? 'Сохранить' : 'Создать')}
          </button>
          <button
            type="button"
            onClick={() => navigate('/catalog')}
            className="btn-secondary"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
};

export default ItemForm;

