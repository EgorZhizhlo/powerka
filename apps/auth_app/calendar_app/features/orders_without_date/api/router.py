from typing import List

from fastapi import (
    APIRouter, HTTPException, status as status_code,
    Depends, Body, Query
)

from sqlalchemy import func, desc, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    RouteSchema, OrderSchema, OrdersPaginated, OrderListParams,
    OrderStatusUpdate
)

from access_control import (
    JwtData,
    check_calendar_access,
    check_active_access_calendar
)

from infrastructure.db.session import async_db_session, async_db_session_begin
from models import OrderModel, RouteModel
from models.associations import (
    employees_routes, employees_cities
)

from core.config import settings


orders_without_date_api_router = APIRouter(
    prefix='/api/orders/without-date'
)


@orders_without_date_api_router.get(
        "/", response_model=OrdersPaginated)
async def list_orders_without_date(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    params: OrderListParams = Depends(),
    employee_data: JwtData = Depends(check_calendar_access),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    q = (
        select(OrderModel)
        .options(
            selectinload(OrderModel.city),
            selectinload(OrderModel.route),
        )
        .where(
            OrderModel.company_id == company_id,
            OrderModel.no_date.is_(True),
            OrderModel.is_active.is_(True),
        )
    )

    if employee_route_ids:
        employee_route_ids.append(None)
        q = q.where(
            or_(
                OrderModel.route_id.in_(employee_route_ids),
                OrderModel.route_id.is_(None),
            )
        )

    if employee_city_ids:
        q = q.where(
            OrderModel.city_id.in_(employee_city_ids)
        )

    if employee_data.status in settings.DISPATCHER2:
        q = q.where(
            OrderModel.dispatcher_id == employee_data.id
        )

    if params.route_id is not None:
        if employee_route_ids and params.route_id not in employee_route_ids:
            return OrdersPaginated(
                total=0, page=params.page,
                page_size=params.page_size,
                total_pages=0, items=[],
            )
        q = q.where(
            OrderModel.route_id == params.route_id
        )

    if params.status is not None:
        q = q.where(
            OrderModel.status == params.status
        )

    total = (
        await session.execute(
            select(
                func.count()
            ).select_from(
                q.subquery()
            )
        )
    ).scalar_one()
    total_pages = (total + params.page_size - 1) // params.page_size

    q = (
        q.order_by(desc(OrderModel.date_of_get))
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )

    orders = (
        await session.execute(q)
    ).scalars().all()

    return OrdersPaginated(
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        items=orders,
    )


@orders_without_date_api_router.get(
    "/routes", response_model=List[RouteSchema]
)
async def list_routes(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    q = (
        select(RouteModel)
        .where(RouteModel.company_id == company_id)
        .order_by(RouteModel.name)
    )

    if employee_route_ids:
        employee_route_ids.append(None)
        q = q.where(
            RouteModel.id.in_(employee_route_ids)
        )

    route_list = await session.scalars(q)
    return route_list.all()


@orders_without_date_api_router.patch(
    "/status",
    response_model=OrderSchema,
)
async def update_order_status(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    payload: OrderStatusUpdate = Body(...),
    employee_data: JwtData = Depends(check_active_access_calendar),
    session: AsyncSession = Depends(async_db_session_begin),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    q = (
        select(OrderModel)
        .options(selectinload(OrderModel.city), selectinload(OrderModel.route))
        .where(
            OrderModel.id == order_id,
            OrderModel.company_id == company_id,
            OrderModel.no_date.is_(True),
            OrderModel.is_active.is_(True),
        )
    )

    if employee_route_ids:
        employee_route_ids.append(None)
        q = q.where(
            or_(
                OrderModel.route_id.in_(employee_route_ids),
                OrderModel.route_id.is_(None),
            )
        )

    if employee_city_ids:
        q = q.where(
            OrderModel.city_id.in_(employee_city_ids)
        )

    order = await session.scalar(q)

    if not order:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена"
        )

    order.status = payload.status
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order
