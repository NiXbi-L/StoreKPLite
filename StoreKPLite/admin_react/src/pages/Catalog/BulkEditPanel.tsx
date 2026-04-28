import React, { useState } from 'react';
import apiClient from '../../utils/apiClient';
import SizeChartCombo from './SizeChartCombo';
import './Catalog.css';

const GENDERS = [
  { value: 'М', label: 'Мужской' },
  { value: 'Ж', label: 'Женский' },
  { value: 'унисекс', label: 'Унисекс' }
];

export type BulkField = '' | 'item_type_id' | 'gender' | 'is_legit' | 'is_legit_false' | 'size_chart_id' | 'size_chart_clear' | 'size' | 'tags' | 'tags_add' | 'price' | 'service_fee_percent' | 'link';

interface ItemTypeOption {
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

interface BulkEditPanelProps {
  selectedIds: number[];
  onSuccess: () => void;
  onClearSelection?: () => void;
  onSelectAll?: () => void;
  itemTypes: ItemTypeOption[];
  sizeCharts: SizeChartOption[];
  fetchSizeCharts: () => Promise<void>;
  setError: (msg: string) => void;
  selectionLabel?: string;
  className?: string;
  totalCount?: number;
}

export function BulkEditPanel({
  selectedIds,
  onSuccess,
  onClearSelection,
  itemTypes,
  sizeCharts,
  fetchSizeCharts,
  setError,
  selectionLabel = 'Массовое изменение:',
  className = 'catalog-bulk-actions',
  onSelectAll,
  totalCount = 0
}: BulkEditPanelProps) {
  const [bulkField, setBulkField] = useState<BulkField>('');
  const [bulkItemTypeId, setBulkItemTypeId] = useState<number | ''>('');
  const [bulkGender, setBulkGender] = useState<string>('');
  const [bulkPrice, setBulkPrice] = useState('');
  const [bulkServiceFee, setBulkServiceFee] = useState('');
  const [bulkLink, setBulkLink] = useState('');
  const [bulkSizeChartId, setBulkSizeChartId] = useState<number | '' | 'new'>('');
  const [editingSizeChartId, setEditingSizeChartId] = useState<number | null>(null);
  const [sizeChartEditLoading, setSizeChartEditLoading] = useState(false);
  const [bulkSizes, setBulkSizes] = useState<string[]>(['']);
  const [bulkTags, setBulkTags] = useState<string[]>(['']);
  const [bulkSizeNumericRange, setBulkSizeNumericRange] = useState({ from: '', to: '' });
  const [bulkSizeIsNumericRange, setBulkSizeIsNumericRange] = useState(false);
  const [loading, setLoading] = useState(false);
  const [newSizeChart, setNewSizeChart] = useState<{ name: string; grid: SizeChartGrid }>({
    name: '',
    grid: { rows: [['']] }
  });
  const [newSizeChartLoading, setNewSizeChartLoading] = useState(false);

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
      await fetchSizeCharts();
      setBulkSizeChartId(res.data.id);
      setNewSizeChart({ name: '', grid: { rows: [['']] } });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания размерной сетки');
    } finally {
      setNewSizeChartLoading(false);
    }
  };

  const startEditSizeChart = async () => {
    const id = typeof bulkSizeChartId === 'number' ? bulkSizeChartId : 0;
    if (!id) return;
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
      await fetchSizeCharts();
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

  const handleDeleteSizeChart = async () => {
    const id = typeof bulkSizeChartId === 'number' ? bulkSizeChartId : 0;
    if (!id || !window.confirm('Удалить эту размерную сетку? У товаров будет сброшена привязка к ней.')) return;
    try {
      setError('');
      await apiClient.delete(`/products/admin/size-charts/${id}`);
      await fetchSizeCharts();
      setBulkSizeChartId('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка удаления');
    }
  };

  const bulkSizeChange = (index: number, value: string) => {
    const next = [...bulkSizes];
    next[index] = value;
    setBulkSizes(next);
  };
  const bulkSizeAdd = () => setBulkSizes([...bulkSizes, '']);
  const bulkSizeRemove = (index: number) => {
    if (bulkSizes.length <= 1) {
      setBulkSizes(['']);
      return;
    }
    setBulkSizes(bulkSizes.filter((_, i) => i !== index));
  };
  const bulkSizeNumericRangeApply = () => {
    const from = parseInt(bulkSizeNumericRange.from, 10);
    const to = parseInt(bulkSizeNumericRange.to, 10);
    if (isNaN(from) || isNaN(to) || from > to) {
      setError('Укажите корректный диапазон (от ≤ до)');
      return;
    }
    const arr: string[] = [];
    for (let i = from; i <= to; i++) arr.push(String(i));
    setBulkSizes(arr);
    setBulkSizeIsNumericRange(false);
    setBulkSizeNumericRange({ from: '', to: '' });
  };

  const bulkTagChange = (index: number, value: string) => {
    const next = [...bulkTags];
    next[index] = value;
    setBulkTags(next);
  };
  const bulkTagAdd = () => setBulkTags([...bulkTags, '']);
  const bulkTagRemove = (index: number) => {
    if (bulkTags.length <= 1) {
      setBulkTags(['']);
      return;
    }
    setBulkTags(bulkTags.filter((_, i) => i !== index));
  };

  const buildPayload = (): Record<string, unknown> | null => {
    const base = { item_ids: selectedIds };
    switch (bulkField) {
      case 'item_type_id':
        if (bulkItemTypeId === '') return null;
        return { ...base, item_type_id: bulkItemTypeId };
      case 'gender':
        if (!bulkGender) return null;
        return { ...base, gender: bulkGender };
      case 'is_legit':
        return { ...base, is_legit: true };
      case 'is_legit_false':
        return { ...base, is_legit: false };
      case 'size_chart_id':
        if (bulkSizeChartId === '' || bulkSizeChartId === 'new') return null;
        return { ...base, size_chart_id: bulkSizeChartId };
      case 'size_chart_clear':
        return { ...base, size_chart_id: null };
      case 'size': {
        const valid = bulkSizes.map(s => s.trim()).filter(Boolean);
        return { ...base, size: valid.length ? valid : null };
      }
      case 'tags': {
        const valid = bulkTags.map(s => s.trim()).filter(Boolean);
        return { ...base, tags: valid.length ? valid : null };
      }
      case 'tags_add': {
        const valid = bulkTags.map(s => s.trim()).filter(Boolean);
        return valid.length ? { ...base, add_tags: valid } : null;
      }
      case 'price': {
        const p = parseFloat(bulkPrice);
        if (isNaN(p) || p < 0) return null;
        return { ...base, price: p };
      }
      case 'service_fee_percent': {
        const f = parseFloat(bulkServiceFee);
        if (isNaN(f) || f < 0) return null;
        return { ...base, service_fee_percent: f };
      }
      case 'link':
        return { ...base, link: bulkLink.trim() || null };
      default:
        return null;
    }
  };

  const handleApply = async () => {
    const payload = buildPayload();
    if (!payload || selectedIds.length === 0) return;
    try {
      setLoading(true);
      setError('');
      await apiClient.patch('/products/admin/items/bulk-update', payload);
      onClearSelection?.();
      setBulkField('');
      setBulkItemTypeId('');
      setBulkGender('');
      setBulkPrice('');
      setBulkServiceFee('');
      setBulkLink('');
      setBulkSizeChartId('');
      setBulkSizes(['']);
      setBulkTags(['']);
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления');
    } finally {
      setLoading(false);
    }
  };

  const canApply = (): boolean => {
    if (selectedIds.length === 0 || loading) return false;
    switch (bulkField) {
      case 'item_type_id': return bulkItemTypeId !== '';
      case 'gender': return !!bulkGender;
      case 'is_legit':
      case 'is_legit_false': return true;
      case 'size_chart_id': return bulkSizeChartId !== '' && bulkSizeChartId !== 'new' && editingSizeChartId == null;
      case 'size_chart_clear': return true;
      case 'size': return true;
      case 'tags': return true; // можно применить и пустой список (сброс тегов)
      case 'tags_add': return bulkTags.some(s => s.trim() !== '');
      case 'price': return bulkPrice.trim() !== '' && !isNaN(parseFloat(bulkPrice)) && parseFloat(bulkPrice) >= 0;
      case 'service_fee_percent': return bulkServiceFee.trim() !== '' && !isNaN(parseFloat(bulkServiceFee)) && parseFloat(bulkServiceFee) >= 0;
      case 'link': return true;
      default: return false;
    }
  };

  const showSizeChartCreate = bulkField === 'size_chart_id' && bulkSizeChartId === 'new';

  return (
    <div className={className}>
      <span className="catalog-bulk-actions-label">
        {selectedIds.length > 0 ? `Выбрано: ${selectedIds.length}` : selectionLabel}
      </span>
      {onSelectAll && (
        <button type="button" className="btn-secondary" onClick={onSelectAll} disabled={totalCount === 0}>
          Выбрать все
        </button>
      )}
      <button type="button" className="btn-secondary" onClick={onClearSelection} disabled={selectedIds.length === 0}>
        Снять выбор
      </button>
      <select
        value={bulkField}
        onChange={(e) => {
          const v = e.target.value as BulkField;
          setBulkField(v);
          if (v !== 'size_chart_id') {
            setBulkSizeChartId('');
            setEditingSizeChartId(null);
            setNewSizeChart({ name: '', grid: { rows: [['']] } });
          }
        }}
        className="catalog-bulk-size-chart-select"
        style={{ minWidth: '160px' }}
      >
        <option value="">— Параметр —</option>
        <option value="item_type_id">Тип товара</option>
        <option value="gender">Пол</option>
        <option value="is_legit">Оригинал/реплика (оригинал)</option>
        <option value="is_legit_false">Оригинал/реплика (реплика)</option>
        <option value="price">Цена (¥)</option>
        <option value="service_fee_percent">Наценка (%)</option>
        <option value="size_chart_id">Таблица размеров</option>
        <option value="size_chart_clear">Таблица размеров (сбросить)</option>
        <option value="size">Размеры (перезапись)</option>
        <option value="tags">Теги (перезапись)</option>
        <option value="tags_add">Теги (добавить)</option>
        <option value="link">Ссылка на товар</option>
      </select>

      {bulkField === 'price' && (
        <input
          type="number"
          step="0.01"
          min="0"
          value={bulkPrice}
          onChange={(e) => setBulkPrice(e.target.value)}
          placeholder="Цена в юанях"
          style={{ width: '100px', padding: '4px 8px' }}
        />
      )}

      {bulkField === 'service_fee_percent' && (
        <input
          type="number"
          step="0.01"
          min="0"
          value={bulkServiceFee}
          onChange={(e) => setBulkServiceFee(e.target.value)}
          placeholder="% наценки"
          style={{ width: '90px', padding: '4px 8px' }}
        />
      )}

      {bulkField === 'link' && (
        <input
          type="url"
          value={bulkLink}
          onChange={(e) => setBulkLink(e.target.value)}
          placeholder="Ссылка на товар (оставьте пустым, чтобы сбросить)"
          style={{ minWidth: '280px', padding: '4px 8px' }}
        />
      )}

      {bulkField === 'item_type_id' && (
        <select
          value={bulkItemTypeId}
          onChange={(e) => setBulkItemTypeId(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          style={{ minWidth: '140px' }}
        >
          <option value="">— тип —</option>
          {itemTypes.map(t => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
      )}

      {bulkField === 'gender' && (
        <select value={bulkGender} onChange={(e) => setBulkGender(e.target.value)} style={{ minWidth: '120px' }}>
          <option value="">— пол —</option>
          {GENDERS.map(g => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>
      )}

      {bulkField === 'size_chart_id' && (
        <>
          <SizeChartCombo
            className="catalog-bulk-size-chart-combo"
            value={bulkSizeChartId === '' ? '' : bulkSizeChartId === 'new' ? 'new' : String(bulkSizeChartId)}
            onChange={(v) => {
              if (v === '') setBulkSizeChartId('');
              else if (v === 'new') setBulkSizeChartId('new');
              else setBulkSizeChartId(parseInt(v, 10));
            }}
            options={sizeCharts}
            noneLabel="— Снять выбор таблицы —"
            createNewLabel="➕ Создать новую таблицу"
            placeholder="Поиск по названию или выберите…"
          />
          {typeof bulkSizeChartId === 'number' && editingSizeChartId == null && (
            <>
              <button type="button" onClick={startEditSizeChart} disabled={sizeChartEditLoading} className="btn-secondary" style={{ padding: '0.35rem 0.75rem' }}>
                {sizeChartEditLoading ? '…' : 'Редактировать'}
              </button>
              <button type="button" onClick={handleDeleteSizeChart} className="btn-delete" style={{ padding: '0.35rem 0.75rem' }}>Удалить сетку</button>
            </>
          )}
          {(showSizeChartCreate || editingSizeChartId != null) && (
            <div style={{ marginTop: '0.5rem', padding: '0.75rem', border: '1px solid #d4d4d4', borderRadius: '8px', background: '#fafafa', display: 'inline-block', verticalAlign: 'top' }}>
              <input
                type="text"
                value={newSizeChart.name}
                onChange={(e) => setNewSizeChart(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Название сетки"
                style={{ width: '180px', marginRight: '0.5rem', marginBottom: '6px', display: 'block' }}
              />
              <div style={{ marginBottom: '6px' }}>
                <button type="button" onClick={sizeChartGridAddRow} className="btn-secondary" style={{ padding: '0.25rem 0.5rem', marginRight: '4px' }}>+ Строка</button>
                <button type="button" onClick={sizeChartGridAddCol} className="btn-secondary" style={{ padding: '0.25rem 0.5rem' }}>+ Столбец</button>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse' }}>
                  <tbody>
                    {newSizeChart.grid.rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => (
                          <td key={ci} style={{ padding: '2px' }}>
                            <input type="text" value={cell} onChange={(e) => sizeChartGridSetCell(ri, ci, e.target.value)} style={{ width: '56px', padding: '2px' }} />
                          </td>
                        ))}
                        <td style={{ padding: '2px' }}><button type="button" onClick={() => sizeChartGridRemoveRow(ri)} className="btn-delete" style={{ padding: '2px 6px' }}>−</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {newSizeChart.grid.rows[0] && newSizeChart.grid.rows[0].length > 1 && (
                <div style={{ marginTop: '4px' }}>
                  Удалить столбец:{' '}
                  {newSizeChart.grid.rows[0].map((_, ci) => (
                    <button key={ci} type="button" onClick={() => sizeChartGridRemoveCol(ci)} className="btn-delete" style={{ padding: '0.2rem 0.4rem', marginRight: '4px' }}>{ci + 1}</button>
                  ))}
                </div>
              )}
              <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {editingSizeChartId != null ? (
                  <>
                    <button type="button" onClick={saveSizeChartEdit} disabled={sizeChartEditLoading} className="btn-primary" style={{ padding: '0.35rem 0.75rem' }}>{sizeChartEditLoading ? '…' : 'Сохранить'}</button>
                    <button type="button" onClick={cancelSizeChartEdit} className="btn-secondary" style={{ padding: '0.35rem 0.75rem' }}>Отмена</button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={createSizeChartAndSelect} disabled={newSizeChartLoading} className="btn-primary" style={{ padding: '0.35rem 0.75rem' }}>{newSizeChartLoading ? '…' : 'Создать и выбрать'}</button>
                    <button type="button" onClick={() => { setBulkSizeChartId(''); setNewSizeChart({ name: '', grid: { rows: [['']] } }); }} className="btn-secondary" style={{ padding: '0.35rem 0.75rem' }}>Отмена</button>
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {bulkField === 'size' && (
        <div style={{ display: 'inline-block', verticalAlign: 'middle' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={bulkSizeIsNumericRange} onChange={(e) => setBulkSizeIsNumericRange(e.target.checked)} />
            <span>Числовой диапазон</span>
          </label>
          {bulkSizeIsNumericRange ? (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <input type="number" placeholder="От" value={bulkSizeNumericRange.from} onChange={(e) => setBulkSizeNumericRange(prev => ({ ...prev, from: e.target.value }))} style={{ width: '70px', padding: '4px' }} />
              <span>—</span>
              <input type="number" placeholder="До" value={bulkSizeNumericRange.to} onChange={(e) => setBulkSizeNumericRange(prev => ({ ...prev, to: e.target.value }))} style={{ width: '70px', padding: '4px' }} />
              <button type="button" onClick={bulkSizeNumericRangeApply} className="btn-secondary" style={{ padding: '0.35rem 0.6rem' }}>Применить</button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
              {bulkSizes.map((s, i) => (
                <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <input type="text" value={s} onChange={(e) => bulkSizeChange(i, e.target.value)} placeholder="Размер" style={{ width: '64px', padding: '4px' }} />
                  {bulkSizes.length > 1 && <button type="button" onClick={() => bulkSizeRemove(i)} className="btn-delete" style={{ padding: '2px 6px' }}>×</button>}
                </span>
              ))}
              <button type="button" onClick={bulkSizeAdd} className="btn-secondary" style={{ padding: '0.35rem 0.6rem' }}>+ Размер</button>
            </div>
          )}
        </div>
      )}

      {(bulkField === 'tags' || bulkField === 'tags_add') && (
        <div style={{ display: 'inline-block', verticalAlign: 'middle' }}>
          <span style={{ marginRight: '0.5rem', fontSize: '0.9em', color: '#666' }}>
            {bulkField === 'tags_add' ? 'Добавить к существующим:' : ''}
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
            {bulkTags.map((t, i) => (
              <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                <input type="text" value={t} onChange={(e) => bulkTagChange(i, e.target.value)} placeholder="Тег" style={{ width: '80px', padding: '4px' }} />
                {bulkTags.length > 1 && <button type="button" onClick={() => bulkTagRemove(i)} className="btn-delete" style={{ padding: '2px 6px' }}>×</button>}
              </span>
            ))}
            <button type="button" onClick={bulkTagAdd} className="btn-secondary" style={{ padding: '0.35rem 0.6rem' }}>+ Тег</button>
          </div>
        </div>
      )}

      {(bulkField === 'is_legit' || bulkField === 'is_legit_false' || bulkField === 'size_chart_clear' || (bulkField && canApply())) && (
        <button
          type="button"
          className="btn-primary"
          onClick={handleApply}
          disabled={!canApply()}
        >
          {loading ? '…' : 'Применить'}
        </button>
      )}
    </div>
  );
}
