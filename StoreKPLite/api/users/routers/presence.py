"""Heartbeat «онлайн» для миниаппа."""
from fastapi import APIRouter, Depends

from api.shared.auth import get_user_id_for_request
from api.users.services.online_presence import touch_user_online

router = APIRouter()


@router.post("/users/me/online")
async def post_user_online(user_id: int = Depends(get_user_id_for_request)):
    """Фронт зовёт раз в несколько минут при активной сессии."""
    await touch_user_online(user_id)
    return {"ok": True}
