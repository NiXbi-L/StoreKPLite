"""Личный кабинет реферала (мини-приложение): статистика по промокодам с привязкой к пользователю."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.database.database import get_session
from api.products.models.promocode import Promocode
from api.products.utils.referral_aggregation import (
    aggregate_referral_for_referrer_in_range,
    current_month_bounds_utc,
    iter_past_month_starts,
)
from api.shared.auth import get_user_id_for_request

router = APIRouter()


class ReferralPromoBrief(BaseModel):
    id: int
    code: str
    commission_percent: float


class ReferralMonthPublic(BaseModel):
    year_month: str
    completed_orders: int
    commission_rub: float


class ReferralDashboardOut(BaseModel):
    eligible: bool
    promocodes: List[ReferralPromoBrief] = Field(default_factory=list)
    current_month: str
    completed_orders_this_month: int = 0
    commission_due_this_month_rub: float = 0.0
    history: List[ReferralMonthPublic] = Field(default_factory=list)
    note: str = (
        "Комиссия считается как процент от суммы «сервисного сбора» по позициям заказа "
        "(как «Ориентировочный доход с продажи» в админке). Учитываются только завершённые заказы. "
        "Месяц — по дате оформления заказа (UTC)."
    )


@router.get("/referral/dashboard", response_model=ReferralDashboardOut)
async def referral_dashboard(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
    history_months: int = Query(12, ge=1, le=24),
):
    r = await session.execute(
        select(Promocode)
        .where(Promocode.referrer_user_id == user_id)
        .order_by(Promocode.id.desc())
    )
    promos = list(r.scalars().all())
    if not promos:
        start, end = current_month_bounds_utc()
        return ReferralDashboardOut(
            eligible=False,
            promocodes=[],
            current_month=start.strftime("%Y-%m"),
            completed_orders_this_month=0,
            commission_due_this_month_rub=0.0,
            history=[],
        )

    brief = [
        ReferralPromoBrief(
            id=p.id,
            code=p.code_normalized,
            commission_percent=float(p.referral_commission_percent or 0),
        )
        for p in promos
    ]
    start, end = current_month_bounds_utc()
    n_m, comm_m = await aggregate_referral_for_referrer_in_range(session, user_id, start, end)
    hist: List[ReferralMonthPublic] = []
    for ms, me, ym in iter_past_month_starts(min(history_months, 24)):
        n, c = await aggregate_referral_for_referrer_in_range(session, user_id, ms, me)
        hist.append(ReferralMonthPublic(year_month=ym, completed_orders=n, commission_rub=float(c)))

    return ReferralDashboardOut(
        eligible=True,
        promocodes=brief,
        current_month=start.strftime("%Y-%m"),
        completed_orders_this_month=n_m,
        commission_due_this_month_rub=float(comm_m),
        history=hist,
    )
