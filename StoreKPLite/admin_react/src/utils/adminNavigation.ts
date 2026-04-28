/**
 * Абсолютные URL и открытие разделов админки в новой вкладке (совпадает с basename в App).
 */
const RAW_BASE = process.env.PUBLIC_URL || '/admin';

export function getAdminAppBase(): string {
  const b = (RAW_BASE || '/admin').replace(/\/$/, '');
  if (!b) return '/admin';
  return b.startsWith('/') ? b : `/${b}`;
}

export function adminAbsoluteUrl(pathWithinAdmin: string): string {
  const base = getAdminAppBase();
  const p = pathWithinAdmin.startsWith('/') ? pathWithinAdmin : `/${pathWithinAdmin}`;
  return `${window.location.origin}${base}${p}`;
}

export function openAdminPath(pathWithinAdmin: string): void {
  window.open(adminAbsoluteUrl(pathWithinAdmin), '_blank', 'noopener,noreferrer');
}
