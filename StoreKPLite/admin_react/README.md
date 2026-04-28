# MatchWear Admin React

React приложение для админ-панели MatchWear.

## Структура проекта

```
admin_react/
├── src/
│   ├── components/        # Общие компоненты
│   │   └── Layout/        # Layout компонент с сайдбаром
│   ├── contexts/          # React Context (AuthContext)
│   ├── pages/             # Страницы приложения
│   │   ├── Login/         # Авторизация
│   │   ├── Dashboard/     # Главная страница
│   │   ├── Users/         # Управление пользователями
│   │   ├── Admins/        # Управление администраторами
│   │   ├── Catalog/       # Каталог товаров
│   │   ├── Orders/        # Заказы
│   │   ├── Finance/       # Финансы
│   │   ├── Delivery/      # Доставка
│   │   ├── FAQ/           # FAQ
│   │   ├── Tickets/       # Тикеты поддержки
│   │   ├── Analytics/     # Аналитика
│   │   └── Database/      # Управление БД
│   └── utils/             # Утилиты
│       └── apiClient.ts   # HTTP клиент для API
├── public/
└── package.json
```

## Каждая страница имеет свою структуру:

```
pages/
  Users/
    ├── Users.tsx          # Основной компонент страницы
    ├── Users.css          # Стили страницы
    ├── components/        # Компоненты, специфичные для этой страницы
    ├── utils/             # Утилиты для этой страницы
    └── hooks/             # Custom hooks (если нужны)
```

## Установка

```bash
cd admin_react
npm install
```

## Запуск

```bash
npm start
```

Приложение запустится на http://localhost:3000

## Сборка

```bash
npm run build
```

## API

Приложение обращается к backend API через proxy (настроен в package.json) или через переменную окружения `REACT_APP_API_URL`.

По умолчанию API запросы идут на `http://localhost:8000`.

## Разработка

Все функциональные страницы находятся в стадии разработки. Базовая структура и роутинг уже настроены.

