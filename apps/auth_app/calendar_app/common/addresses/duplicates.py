from typing import Optional
from datetime import date as Date
from fastapi import HTTPException, status as status_code
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from models import OrderModel
from apps.calendar_app.common.addresses.normalizer import address_key


async def ensure_no_duplicate_address(
    db: AsyncSession,
    company_id: int,
    city_id: int,
    address: str,
    date: Optional[Date],
    exclude_order_id: Optional[int] = None,
):
    """
    Логика: если date задана — проверяем заявки на эту дату (и no_date=False).
            если date не задана — проверяем только среди заявок с no_date=True.
    Сравнение — по каноническому ключу адреса.
    """
    q = (
        select(OrderModel)
        .where(
            OrderModel.company_id == company_id,
            OrderModel.city_id == city_id,
            OrderModel.is_active.is_(True),
        )
    )
    if date is not None:
        q = q.where(OrderModel.date == date, OrderModel.no_date.is_(False))
    else:
        q = q.where(OrderModel.no_date.is_(True))

    if exclude_order_id is not None:
        q = q.where(OrderModel.id != exclude_order_id)

    existing_orders = (await db.execute(q)).scalars().all()

    target_key = address_key(address)

    for o in existing_orders:
        if address_key(o.address) == target_key:
            raise HTTPException(
                status_code=status_code.HTTP_400_BAD_REQUEST,
                detail="Похожая заявка в этом же городе"
                f" уже существует (адрес: {o.address})"
            )
