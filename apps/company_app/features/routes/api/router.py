import math
from fastapi import (
    APIRouter, Response, status as status_code,
    Query, Depends, Body
)

from sqlalchemy import select, func, exists
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import CustomHTTPException, check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from models import RouteModel, RouteStatisticModel

from apps.company_app.schemas.routes import (
    RouteForm, RouteOut, RoutesPage
)


routes_api_router = APIRouter(
    prefix="/api/routes"
)


@routes_api_router.get("/", response_model=RoutesPage)
async def api_get_routes(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    filters = [RouteModel.company_id == company_id]
    if search:
        filters.append(RouteModel.name.ilike(f"%{search}%"))

    total = (await session.execute(
        select(func.count(RouteModel.id)).where(*filters)
    )).scalar_one()

    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    rows = (await session.execute(
        select(RouteModel)
        .where(*filters)
        .order_by(
            RouteModel.is_deleted.isnot(True).desc(),
            RouteModel.id.desc()
        )
        .limit(per_page).offset(offset)
    )).scalars().all()

    items = []
    for obj in rows:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = RouteOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(RouteOut(**item_dict))

    return RoutesPage(items=items, page=page, total_pages=total_pages)


@routes_api_router.post("/create")
async def api_create_route(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_data: RouteForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    # уникальность имени
    exists_q = await session.execute(
        select(exists()
               .where(func.lower(RouteModel.name) == func.lower(route_data.name),
                      RouteModel.company_id == company_id))
    )
    if exists_q.scalar_one():
        raise CustomHTTPException(
            company_id=company_id,
            status_code=404,
            detail=f"Маршрут {route_data.name} уже существует!"
        )

    new = RouteModel(
        name=route_data.name,
        day_limit=route_data.day_limit,
        color=route_data.color,
        company_id=company_id
    )
    session.add(new)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@routes_api_router.put("/update")
async def api_update_route(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_id: int = Query(..., ge=1, le=settings.max_int),
    route_data: RouteForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    dup = await session.execute(
        select(exists().where(
            func.lower(RouteModel.name) == func.lower(route_data.name),
            RouteModel.company_id == company_id,
            RouteModel.id != route_id)
        )
    )
    if dup.scalar_one():
        raise CustomHTTPException(
            company_id=company_id,
            status_code=404,
            detail=f"Маршрут {route_data.name} уже существует!"
        )

    route = (await session.execute(
        select(RouteModel)
        .where(
            RouteModel.id == route_id,
            RouteModel.company_id == company_id)
    )).scalar_one_or_none()
    await check_is_none(
        route, type="Маршрут", id=route_id, company_id=company_id)

    route_statistics = (
        await session.execute(
            select(RouteStatisticModel)
            .where(
                RouteStatisticModel.route_id == route_id
            )
            .with_for_update()
        )
    ).scalars().all()

    new_day_limit = route_data.day_limit
    old_day_limit = route.day_limit

    for route_statistic in route_statistics:
        route_statistic_free_limit = route_statistic.day_limit_free
        d = route_statistic_free_limit - old_day_limit
        route_statistic.day_limit_free = new_day_limit + d

    route.name = route_data.name
    route.day_limit = new_day_limit
    route.color = route_data.color

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@routes_api_router.delete("/delete")
async def api_delete_route(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    route = (
        await session.execute(
            select(RouteModel)
            .where(
                RouteModel.id == route_id,
                RouteModel.company_id == company_id)
            .options(
                selectinload(RouteModel.order),
                selectinload(RouteModel.employees),
                selectinload(RouteModel.assignments),
                selectinload(RouteModel.route_statistic),
                selectinload(RouteModel.route_addition),
            )
        )
    ).scalar_one_or_none()

    await check_is_none(
        route, type="Маршрут", id=route_id, company_id=company_id
    )

    has_orders = bool(route.order)

    # Всегда разрываем связь с сотрудниками
    route.employees.clear()

    if has_orders:
        # мягкое удаление
        route.is_deleted = True
    else:
        # жёсткое удаление (каскады сработают)
        await session.delete(route)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@routes_api_router.post("/restore")
async def api_restore_route(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    route = (await session.execute(
        select(RouteModel)
        .where(RouteModel.id == route_id,
               RouteModel.company_id == company_id,
               RouteModel.is_deleted.is_(True))
    )).scalar_one_or_none()

    await check_is_none(
        route, type="Маршрут", id=route_id, company_id=company_id
    )

    route.is_deleted = False

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
