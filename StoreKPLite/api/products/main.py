"""
FastAPI приложение для микросервиса товаров
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.shared.cors import cors_allowed_origins
from api.products.database.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Products Service",
    description="Микросервис товаров MatchWear",
    version="1.0.0",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    try:
        await init_db()
        logger.info("База данных сервиса товаров инициализирована")
        
        # Обновляем историю цен для всех товаров при старте системы
        try:
            from api.products.database.database import async_session_maker
            from api.products.routers.price_history import (
                delete_price_history_older_than_days,
                calculate_item_price,
                upsert_price_history_4h_bucket,
            )
            from api.products.utils.finance_context import get_finance_price_context
            from api.products.models.item import Item
            from sqlalchemy import select
            
            async with async_session_maker() as session:
                ctx = await get_finance_price_context()
                
                items_result = await session.execute(select(Item))
                items = items_result.scalars().all()
                updated_count = 0
                created_count = 0
                for item in items:
                    new_price_rub = await calculate_item_price(item, ctx)
                    if await upsert_price_history_4h_bucket(session, item.id, new_price_rub):
                        created_count += 1
                    else:
                        updated_count += 1
                
                await delete_price_history_older_than_days(session, days=7)
                await session.commit()
                logger.info(f"История цен обновлена при старте: обновлено {updated_count}, создано {created_count} записей")
        except Exception as e:
            logger.error(f"Ошибка при обновлении истории цен при старте: {e}", exc_info=True)
            # Не прерываем запуск системы, если не удалось обновить историю цен
    except Exception:
        logger.exception("Ошибка при инициализации БД products-service; прерываем старт")
        raise


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "products"}


# Подключаем роутеры
from api.products.routers import (
    feed,
    actions,
    cart,
    orders,
    items,
    likes,
    admin,
    price_history,
    delivery_local_admin_proxy,
    analytics,
    cascade_delete,
    item_types,
    reviews,
    share_catalog,
)

app.include_router(feed.router, tags=["feed"])
app.include_router(share_catalog.router, tags=["share"])
app.include_router(items.router, tags=["items"])
app.include_router(reviews.router)
app.include_router(actions.router, tags=["actions"])
app.include_router(likes.router, tags=["likes"])
app.include_router(cart.router, tags=["cart"])
app.include_router(orders.router, tags=["orders"])
app.include_router(admin.router, tags=["admin"])
app.include_router(item_types.router, tags=["item-types"])
app.include_router(price_history.router, tags=["internal"])
app.include_router(delivery_local_admin_proxy.router, tags=["delivery-local-admin-proxy"])
app.include_router(analytics.router, tags=["internal"])
app.include_router(cascade_delete.router, tags=["internal"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

