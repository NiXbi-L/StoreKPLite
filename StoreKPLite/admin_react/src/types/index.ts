// Типы для API ответов
export interface User {
  id: number;
  tgid: number;
  vkid?: number;
  username?: string;
  full_name?: string;
  gender?: string;
  created_at: string;
}

export interface Admin {
  id: number;
  tgid: number;
  login: string;
  admin_type: string;
}

export interface Item {
  id: number;
  name: string;
  description?: string;
  price: number;
  item_type: string;
  gender: string;
  sizes?: string;
  created_at: string;
}

export interface Order {
  id: number;
  user_id: number;
  order_data: any;
  created_at: string;
}

