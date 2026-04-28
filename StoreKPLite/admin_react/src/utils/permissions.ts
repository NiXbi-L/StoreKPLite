/**
 * StoreKPLite: минимальная админка (каталог, заказы, админы, пользователи).
 */

export type SectionKey = 'users' | 'admins' | 'admin_roles' | 'catalog' | 'orders';

export interface SectionPermission {
  key: SectionKey;
  name: string;
  icon: string;
  path: string;
  description: string;
}

export const SECTION_PERMISSIONS: Record<SectionKey, SectionPermission> = {
  users: {
    key: 'users',
    name: 'Пользователи',
    icon: '👥',
    path: 'users',
    description: 'Управление пользователями системы',
  },
  admins: {
    key: 'admins',
    name: 'Администраторы',
    icon: '👤',
    path: 'admins',
    description: 'Сотрудники и вход в админку',
  },
  admin_roles: {
    key: 'admin_roles',
    name: 'Роли доступа',
    icon: '🔐',
    path: 'admin-roles',
    description: 'Наборы прав; сотруднику назначается роль',
  },
  catalog: {
    key: 'catalog',
    name: 'Каталог',
    icon: '📦',
    path: 'catalog',
    description: 'Управление товарами и каталогом',
  },
  orders: {
    key: 'orders',
    name: 'Заказы',
    icon: '🛒',
    path: 'orders',
    description: 'Управление заказами',
  },
};

const SECTION_SIDEBAR_ANY_OF: Record<SectionKey, string[] | null> = {
  users: ['users'],
  admins: null,
  admin_roles: null,
  catalog: ['catalog'],
  orders: ['orders'],
};

function parsePermissions(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem('admin_permissions');
    if (!raw) return {};
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') return {};
    return data as Record<string, boolean>;
  } catch {
    return {};
  }
}

export function isOwner(): boolean {
  return (localStorage.getItem('admin_type') || '').toLowerCase() === 'owner';
}

export function hasPermission(key: string): boolean {
  if (isOwner()) return true;
  return Boolean(parsePermissions()[key]);
}

export function hasAnyPermission(keys: string[]): boolean {
  if (isOwner()) return true;
  return keys.some((k) => hasPermission(k));
}

export function getRoleLabel(): string {
  if (isOwner()) return 'Владелец';
  const t = (localStorage.getItem('admin_role_title') || '').trim();
  return t || 'Сотрудник';
}

export function getAvailableSections(): SectionPermission[] {
  return Object.values(SECTION_PERMISSIONS).filter((section) => {
    if (section.key === 'admins' || section.key === 'admin_roles') return isOwner();
    const keys = SECTION_SIDEBAR_ANY_OF[section.key];
    if (!keys?.length) return false;
    return hasAnyPermission(keys);
  });
}

export function defaultRoutePermissions(sectionKey: SectionKey): string[] {
  if (sectionKey === 'admins' || sectionKey === 'admin_roles') return [];
  return [sectionKey];
}

export function persistAdminSessionFromApi(data: {
  admin_type?: string;
  role_title?: string | null;
  permissions?: Record<string, boolean> | null;
}): void {
  if (data.admin_type) {
    localStorage.setItem('admin_type', data.admin_type);
  }
  if (data.role_title != null) {
    localStorage.setItem('admin_role_title', (data.role_title || '').trim());
  }
  if (data.permissions != null) {
    localStorage.setItem('admin_permissions', JSON.stringify(data.permissions));
  }
}

export function clearAdminPermissionCache(): void {
  localStorage.removeItem('admin_permissions');
  localStorage.removeItem('admin_role_title');
}
