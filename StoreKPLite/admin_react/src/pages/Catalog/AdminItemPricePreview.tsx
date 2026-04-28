import React from 'react';
import type { AdminItemPricePreviewData } from '../../utils/useAdminItemPricePreview';

interface AdminItemPricePreviewProps {
  preview: AdminItemPricePreviewData | null;
  loading: boolean;
  /** Подсказка, если нельзя посчитать (нет цены в ¥ и т.п.) */
  idleMessage?: string;
}

const AdminItemPricePreview: React.FC<AdminItemPricePreviewProps> = ({
  preview,
  loading,
  idleMessage,
}) => {
  if (loading) {
    return (
      <div className="item-price-preview item-price-preview--muted" aria-live="polite">
        Расчёт цены…
      </div>
    );
  }
  if (!preview) {
    if (!idleMessage) return null;
    return (
      <div className="item-price-preview item-price-preview--muted" aria-live="polite">
        {idleMessage}
      </div>
    );
  }
  return (
    <div className="item-price-preview" role="status" aria-live="polite">
      <div className="item-price-preview__line">
        <span className="item-price-preview__label">Цена для клиента</span>
        <strong className="item-price-preview__value">{preview.current_price_rub.toFixed(2)} ₽</strong>
      </div>
      <div className="item-price-preview__line item-price-preview__line--income">
        <span className="item-price-preview__label">Ориентировочный доход с продажи</span>
        <strong className="item-price-preview__value">{preview.service_fee_amount.toFixed(2)} ₽</strong>
      </div>
      <p className="item-price-preview__note">
        Как в каталоге админки: курс с маржой, наценка на юани, доставка за кг (если указан вес), сервисный
        процент, коэффициент эквайринга.
      </p>
    </div>
  );
};

export default AdminItemPricePreview;
