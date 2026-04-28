from sqlalchemy.ext.asyncio import AsyncSession

from api.users.models.app_runtime_settings import AppRuntimeSettings


async def get_runtime_settings_row(session: AsyncSession) -> AppRuntimeSettings:
    row = await session.get(AppRuntimeSettings, 1)
    if row is None:
        row = AppRuntimeSettings(id=1, miniapp_admin_only=False)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def is_miniapp_admin_only(session: AsyncSession) -> bool:
    row = await get_runtime_settings_row(session)
    return bool(row.miniapp_admin_only)


def default_guest_html() -> str:
    return """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Временно недоступно</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 2rem;
           background: #f4f4f5; color: #18181b; text-align: center; }
    h1 { font-size: 1.25rem; font-weight: 600; }
    p { color: #52525b; max-width: 24rem; margin: 1rem auto; line-height: 1.5; }
  </style>
</head>
<body>
  <h1>Сервис временно недоступен</h1>
  <p>Ведутся технические работы. Пожалуйста, зайдите позже.</p>
</body>
</html>"""
