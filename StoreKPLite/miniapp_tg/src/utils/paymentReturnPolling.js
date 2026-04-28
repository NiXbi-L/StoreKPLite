import { getOrder } from '../api/products';
import { isTelegramWebAppEnvironment } from './telegramEnvironment';

const DEFAULT_ORDER_INTERVAL_MS = 4000;
const DEFAULT_MAX_MS = 180000;

/**
 * Подписка на возврат во вью миниаппа (страница снова видна).
 * @returns {() => void} отписка
 */
export function attachMiniappResumeListener(onResume) {
  const run = () => {
    if (document.visibilityState === 'visible') onResume();
  };
  document.addEventListener('visibilitychange', run);
  const tg = isTelegramWebAppEnvironment() ? window.Telegram?.WebApp : null;
  let tgOff = () => {};
  if (tg?.onEvent) {
    const h = () => onResume();
    try {
      tg.onEvent('visibilityChanged', h);
      tgOff = () => {
        try {
          tg.offEvent?.('visibilityChanged', h);
        } catch {
          /* ignore */
        }
      };
    } catch {
      /* ignore */
    }
  }
  return () => {
    document.removeEventListener('visibilitychange', run);
    tgOff();
  };
}

export function isOrderFullyPaid(order, expectedTotalRub) {
  const paid = Number(order?.paid_amount ?? 0);
  const total = Number(expectedTotalRub ?? order?.order_total ?? 0);
  return Number.isFinite(paid) && Number.isFinite(total) && total - paid <= 0.02;
}

/**
 * Периодически запрашивает заказ, пока не оплачен полностью или не истечёт время.
 * @returns {() => void} stop
 */
export function startOrderPaymentPolling({
  orderId,
  expectedTotalRub,
  onTick,
  onPaid,
  intervalMs = DEFAULT_ORDER_INTERVAL_MS,
  maxDurationMs = DEFAULT_MAX_MS,
}) {
  let stopped = false;
  let detachResume = () => {};

  const stop = () => {
    if (stopped) return;
    stopped = true;
    clearInterval(intervalId);
    clearTimeout(maxTimerId);
    detachResume();
  };

  const run = async () => {
    if (stopped) return;
    try {
      const order = await getOrder(orderId);
      onTick?.(order);
      if (isOrderFullyPaid(order, expectedTotalRub)) {
        stop();
        onPaid?.(order);
      }
    } catch {
      /* сеть / 401 — следующий тик */
    }
  };

  const intervalId = setInterval(run, intervalMs);
  const maxTimerId = setTimeout(stop, maxDurationMs);
  detachResume = attachMiniappResumeListener(run);
  run();

  return stop;
}
