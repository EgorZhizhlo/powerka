import re
from typing import Optional

from fastapi import (
    APIRouter, HTTPException, status as status_code,
    Query, Depends
)

from sqlalchemy import func, or_, select
from sqlalchemy.orm import contains_eager
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_calendar_access
)

from core.config import settings

from infrastructure.db import async_db_session

from models import OrderModel, CityModel
from models.associations import employees_routes, employees_cities

from apps.calendar_app.schemas.orders_search import (
    OrdersPaginated, OrderSchema
)


orders_search_api_router = APIRouter(
    prefix='/api/orders/search')


@orders_search_api_router.get("/", response_model=OrdersPaginated)
async def api_search_list(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_id: Optional[int] = Query(None),
    status: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    search_query: str = Query(..., min_length=1),
    employee_data: JwtData = Depends(check_calendar_access),
    session: AsyncSession = Depends(async_db_session),
):
    sq = search_query.strip()
    if not sq:
        raise HTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            detail="Строка поиска не должна быть пустой"
        )

    text_term = f"%{sq.lower()}%"
    digit_search = "".join(re.findall(r"\d+", sq))
    phone_term = f"%{digit_search}%"

    cities_q = await session.scalars(
        select(employees_cities.c.city_id)
        .where(employees_cities.c.employee_id == employee_data.id)
    )
    employee_city_ids = cities_q.all()

    route_q = await session.scalars(
        select(employees_routes.c.route_id)
        .where(employees_routes.c.employee_id == employee_data.id)
    )
    employee_route_ids = route_q.all()

    stmt = (
        select(OrderModel)
        .outerjoin(OrderModel.city)
        .options(contains_eager(OrderModel.city))
        .where(
            OrderModel.company_id == company_id,
        )
    )

    if employee_data.status in settings.DISPATCHER2:
        stmt = stmt.where(OrderModel.is_active.is_(True))

    if employee_route_ids:
        stmt = (
            stmt
            .where(
                or_(
                    OrderModel.route_id.in_(employee_route_ids),
                    OrderModel.route_id.is_(None)
                )
            )
        )
    if employee_city_ids:
        stmt = stmt.where(
            OrderModel.city_id.in_(employee_city_ids)
        )
    if route_id:
        stmt = stmt.where(OrderModel.route_id == route_id)
    if status:
        stmt = stmt.where(OrderModel.status == status)

    cleaned_phone = func.replace(
        func.replace(
            func.replace(
                func.replace(OrderModel.phone_number, ' ', ''),
                '(', ''),
            ')', ''),
        '-', ''
    )
    cleaned_sec_phone = func.coalesce(
        func.replace(
            func.replace(
                func.replace(
                    func.replace(OrderModel.sec_phone_number, ' ', ''),
                    '(', ''),
                ')', ''),
            '-', ''
        ),
        ''
    )

    conditions = [
        OrderModel.address.ilike(text_term),
        OrderModel.additional_info.ilike(text_term),
        CityModel.name.ilike(text_term),
    ]

    phone_pattern = r'^[\d\+\-\s\(\)]+$'
    if digit_search and re.match(phone_pattern, sq):
        conditions.append(or_(
            cleaned_phone.ilike(phone_term),
            cleaned_sec_phone.ilike(phone_term)
        ))

    stmt = stmt.where(or_(*conditions))

    count_q = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(OrderModel.id.asc()).offset(offset).limit(page_size)

    result = await session.execute(stmt)
    orders = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size
    return OrdersPaginated(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[OrderSchema.model_validate(o) for o in orders],
    )
