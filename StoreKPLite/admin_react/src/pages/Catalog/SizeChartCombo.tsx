import React, { useState, useEffect, useMemo, useRef } from 'react';

export interface SizeChartComboOption {
  id: number;
  name: string;
}

export interface SizeChartComboProps {
  /** '' | 'new' | id as string */
  value: string;
  onChange: (value: string) => void;
  options: SizeChartComboOption[];
  disabled?: boolean;
  noneLabel?: string;
  createNewLabel?: string;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
}

const defaultNone = '— Без размерной сетки —';
const defaultCreate = '➕ Создать новую таблицу';
const defaultPlaceholder = 'Введите название для поиска или выберите из списка…';

/**
 * Выбор размерной сетки: сверху «создать новую», затем «без сетки», затем список с фильтром по вводу.
 */
const SizeChartCombo: React.FC<SizeChartComboProps> = ({
  value,
  onChange,
  options,
  disabled = false,
  noneLabel = defaultNone,
  createNewLabel = defaultCreate,
  placeholder = defaultPlaceholder,
  className = '',
  inputClassName = '',
}) => {
  const [inputValue, setInputValue] = useState('');
  const [open, setOpen] = useState(false);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (value === 'new') {
      setInputValue('');
      return;
    }
    if (value === '') {
      if (!open) setInputValue('');
      return;
    }
    const o = options.find((x) => String(x.id) === value);
    setInputValue(o?.name ?? '');
  }, [value, options, open]);

  const filtered = useMemo(() => {
    const q = inputValue.trim().toLowerCase();
    if (!q || value === 'new') return options;
    return options.filter((o) => o.name.toLowerCase().includes(q));
  }, [options, inputValue, value]);

  const inputDisplay = value === 'new' ? createNewLabel : inputValue;

  const clearBlurTimer = () => {
    if (blurTimer.current != null) {
      clearTimeout(blurTimer.current);
      blurTimer.current = null;
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (disabled) return;
    const t = e.target.value;
    setOpen(true);
    if (value === 'new') {
      onChange('');
      setInputValue(t);
      return;
    }
    setInputValue(t);
    if (t.trim() === '') {
      onChange('');
      return;
    }
    if (value && value !== 'new') {
      const cur = options.find((o) => String(o.id) === value);
      if (!cur || t !== cur.name) onChange('');
    }
  };

  const pick = (next: string, label?: string) => {
    clearBlurTimer();
    onChange(next);
    if (next === '') setInputValue('');
    else if (next === 'new') setInputValue('');
    else if (label != null) setInputValue(label);
    setOpen(false);
  };

  return (
    <div className={`size-chart-combo ${className}`.trim()}>
      <input
        type="text"
        className={`size-chart-combo__input ${inputClassName}`.trim()}
        value={inputDisplay}
        onChange={handleInputChange}
        onFocus={() => {
          clearBlurTimer();
          if (!disabled) setOpen(true);
        }}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        aria-expanded={open}
        aria-haspopup="listbox"
      />
      {open && !disabled && (
        <div
          className="size-chart-combo__dropdown"
          role="listbox"
          onMouseDown={(e) => e.preventDefault()}
        >
          <button
            type="button"
            role="option"
            className="size-chart-combo__item size-chart-combo__item--action"
            onClick={() => pick('new')}
          >
            {createNewLabel}
          </button>
          <button
            type="button"
            role="option"
            className="size-chart-combo__item size-chart-combo__item--muted"
            onClick={() => pick('')}
          >
            {noneLabel}
          </button>
          {filtered.length === 0 ? (
            <div className="size-chart-combo__empty">Нет совпадений</div>
          ) : (
            filtered.map((c) => (
              <button
                key={c.id}
                type="button"
                role="option"
                className="size-chart-combo__item"
                onClick={() => pick(String(c.id), c.name)}
              >
                {c.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default SizeChartCombo;
