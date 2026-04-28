"""Одноразовый тест CDEK (запуск: python -m api.delivery._test_cdek)."""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from api.delivery.cdek import get_cdek_token, get_delivery_points, resolve_city_code

async def main():
    token = await get_cdek_token()
    print("Token OK, len =", len(token))
    code = await resolve_city_code("Москва")
    print("Москва city_code:", code)
    if code:
        points = await get_delivery_points(code)
        print("PVZ count:", len(points))
        if points:
            print("First item keys:", list(points[0].keys())[:12])

if __name__ == "__main__":
    asyncio.run(main())
