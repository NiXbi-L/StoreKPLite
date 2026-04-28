/**
 * StoreKPLite: продуктовая аналитика отключена (отдельный stats-service удалён).
 * API track/init/shutdown оставлены, чтобы не трогать вызовы в страницах.
 */

export function track(_name, _props) {
  /* no-op */
}

export async function flushProductAnalytics() {
  /* no-op */
}

export function initProductAnalytics() {
  /* no-op */
}

export function shutdownProductAnalytics() {
  /* no-op */
}
