from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date as date_

from models.associations import employees_cities, employees_routes
from models import OrderModel

from core.config import settings


async def get_calendar_order(
    session: AsyncSession,
    user_status: str,
    company_id: int,
    target_date: date_ = None,
    order_id: int = None,
    dispatcher_id: int = None,
    for_update: bool = False,
    only_active: bool = True
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == dispatcher_id)
        )
    ).scalars().all()

    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == dispatcher_id)
        )
    ).scalars().all()

    user_orders_query = (
        select(
            OrderModel
        ).where(
            OrderModel.company_id == company_id,
        ).options(
            selectinload(OrderModel.route),
            selectinload(OrderModel.city)
        )
    )

    if only_active:
        user_orders_query = user_orders_query.where(
            OrderModel.is_active.is_(True),
        )

    if employee_route_ids:
        user_orders_query = (
            user_orders_query
            .where(
                or_(
                    OrderModel.route_id.in_(employee_route_ids),
                    OrderModel.route_id.is_(None)
                )
            )
        )

    if employee_city_ids:
        user_orders_query = user_orders_query.where(
            OrderModel.city_id.in_(employee_city_ids)
        )

    if target_date is not None:
        user_orders_query = user_orders_query.where(
            OrderModel.date == target_date,
            OrderModel.no_date.is_(False)
        )
    if order_id:
        user_orders_query = user_orders_query.where(
            OrderModel.id == order_id
        )
    if user_status in settings.DISPATCHER2:
        user_orders_query = user_orders_query.where(
            OrderModel.dispatcher_id == dispatcher_id)

    if order_id and for_update:
        user_orders_query = user_orders_query.with_for_update()

    if order_id:
        user_orders = (
            await session.execute(user_orders_query)).scalar_one_or_none()
    else:
        user_orders = (
            await session.execute(user_orders_query)).scalars().all()
    return user_orders


def get_route_key(order: OrderModel) -> str:
    return order.route.name if order.route else ""


def sorting_key(order: OrderModel):
    if order.weight is not None and order.weight >= 1:
        return (0, order.weight, order.id)
    else:
        return (1, 0, order.id)


async def _load_orders(
    session: AsyncSession,
    company_id: int,
    date: date_,
    order_ids: list[int]
) -> dict[int, OrderModel]:
    if not order_ids:
        return {}
    orders = (
        await session.execute(
            select(OrderModel)
            .where(
                OrderModel.company_id == company_id,
                OrderModel.date == date,
                OrderModel.id.in_(order_ids)
            )
            .order_by(OrderModel.id)
            .with_for_update()
        )
    ).scalars().all()
    return {o.id: o for o in orders}
