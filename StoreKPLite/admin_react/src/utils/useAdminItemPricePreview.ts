import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import apiClient from './apiClient';

export interface AdminItemPricePreviewData {
  current_price_rub: number;
  service_fee_amount: number;
}

export interface UseAdminItemPricePreviewArgs {
  price: string;
  service_fee_percent: string;
  estimated_weight_kg: string;
}

/**
 * Дебаунс-превью цены: тот же расчёт, что на бэкенде (каталог / карточка админки).
 */
export function useAdminItemPricePreview(args: UseAdminItemPricePreviewArgs): {
  preview: AdminItemPricePreviewData | null;
  loading: boolean;
} {
  const [preview, setPreview] = useState<AdminItemPricePreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const requestSeq = useRef(0);

  useEffect(() => {
    const priceTrim = args.price.trim();
    const priceNum = parseFloat(priceTrim.replace(',', '.'));
    if (!priceTrim || Number.isNaN(priceNum) || priceNum < 0) {
      setPreview(null);
      setLoading(false);
      return;
    }

    const feeNum = parseFloat(String(args.service_fee_percent).trim().replace(',', '.'));
    const fee = Number.isNaN(feeNum) || feeNum < 0 ? 0 : feeNum;

    const wTrim = args.estimated_weight_kg.trim();
    let estimated_weight_kg: number | undefined;
    if (wTrim !== '') {
      const w = parseFloat(wTrim.replace(',', '.'));
      if (Number.isNaN(w) || w < 0) {
        setPreview(null);
        setLoading(false);
        return;
      }
      estimated_weight_kg = w;
    }

    const ac = new AbortController();
    const seq = ++requestSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true);
        try {
          const body: Record<string, number> = {
            price: priceNum,
            service_fee_percent: fee,
          };
          if (estimated_weight_kg !== undefined) {
            body.estimated_weight_kg = estimated_weight_kg;
          }
          const res = await apiClient.post<AdminItemPricePreviewData>(
            '/products/admin/items/price-preview',
            body,
            { signal: ac.signal },
          );
          if (seq !== requestSeq.current) return;
          const cur = Number(res.data.current_price_rub);
          const svc = Number(res.data.service_fee_amount);
          if (!Number.isFinite(cur) || !Number.isFinite(svc)) {
            setPreview(null);
          } else {
            setPreview({ current_price_rub: cur, service_fee_amount: svc });
          }
        } catch (e: unknown) {
          if (axios.isAxiosError(e) && e.code === 'ERR_CANCELED') {
            return;
          }
          if (seq === requestSeq.current) {
            setPreview(null);
          }
        } finally {
          if (seq === requestSeq.current) {
            setLoading(false);
          }
        }
      })();
    }, 380);

    return () => {
      window.clearTimeout(timer);
      requestSeq.current += 1;
      ac.abort();
    };
  }, [args.price, args.service_fee_percent, args.estimated_weight_kg]);

  return { preview, loading };
}
