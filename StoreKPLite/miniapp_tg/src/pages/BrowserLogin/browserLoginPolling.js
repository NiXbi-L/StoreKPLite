import { getUsersApiBase } from '../../utils/miniappAdminOnly';

const POLL_MS = 2000;

/**
 * @param {string} code
 * @param {{ onReady: (code: string) => void | Promise<void>, onForbidden: () => void, onError: (e: Error) => void }} handlers
 * @returns {() => void} stop
 */
export function startBrowserLoginPolling(code, { onReady, onForbidden, onError }) {
  const base = getUsersApiBase();
  let stopped = false;
  const id = setInterval(async () => {
    if (stopped) return;
    try {
      const st = await fetch(`${base}/auth/browser-login/status?code=${encodeURIComponent(code)}`);
      const j = await st.json().catch(() => ({}));
      if (j.status === 'ready') {
        stopped = true;
        clearInterval(id);
        await onReady(code);
      } else if (j.status === 'forbidden') {
        stopped = true;
        clearInterval(id);
        onForbidden();
      }
    } catch (e) {
      stopped = true;
      clearInterval(id);
      onError(e instanceof Error ? e : new Error(String(e)));
    }
  }, POLL_MS);
  return () => {
    stopped = true;
    clearInterval(id);
  };
}
