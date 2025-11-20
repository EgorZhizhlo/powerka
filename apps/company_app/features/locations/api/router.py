from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import CustomHTTPException
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import (
    NotFoundError, BadRequestError, ForbiddenError
)

from infrastructure.db import async_db_session, async_db_session_begin

from models import LocationModel

from apps.company_app.schemas.locations import (
    LocationForm, LocationsPage, LocationOut
)


locations_api_router = APIRouter(
    prefix="/api/locations"
)


@locations_api_router.get(
    "/",
    response_model=LocationsPage,
)
async def api_get_locations(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    search_clause = LocationModel.name.ilike(f"%{search}%")

    total = (
        await session.execute(
            select(func.count(LocationModel.id)).where(
                LocationModel.company_id == company_id,
                search_clause,
            )
        )
    ).scalar_one()

    import math
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    stmt = (
        select(LocationModel)
        .where(
            LocationModel.company_id == company_id,
            search_clause,
        )
        .order_by(
            LocationModel.is_deleted.isnot(True).desc(),
            LocationModel.id.desc(),
        )
        .limit(per_page)
        .offset(offset)
    )

    result = await session.execute(stmt)
    objs = result.scalars().all()

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = LocationOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(LocationOut(**item_dict))

    return {
        "items": items,
        "page": page,
        "total_pages": total_pages,
    }


@locations_api_router.post("/create")
async def api_create_location(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    location_data: LocationForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    location = LocationModel()

    for field, value in location_data.model_dump().items():
        setattr(location, field, value)

    location.company_id = company_id
    session.add(location)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@locations_api_router.put("/update")
async def api_update_location(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    location_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    location_data: LocationForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):

    location = (
        await session.execute(
            select(LocationModel)
            .where(
                LocationModel.company_id == company_id,
                LocationModel.id == location_id
            )
        )
    ).scalar_one_or_none()

    if not location:
        raise NotFoundError(
            detail="Расположение счетчика не найдено!"
        )

    for field, value in location_data.model_dump().items():
        setattr(location, field, value)

    session.add(location)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@locations_api_router.delete("/delete")
async def api_delete_location(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    location_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    location = (
        await session.execute(
            select(LocationModel)
            .where(
                LocationModel.id == location_id,
                LocationModel.company_id == company_id,
                LocationModel.is_deleted.isnot(True),
            )
            .options(selectinload(LocationModel.verifications))
        )
    ).scalar_one_or_none()

    if not location:
        raise NotFoundError(
            detail="Расположение счетчика не найдено!"
        )

    can_hard_delete = not location.verifications

    if can_hard_delete:
        await session.delete(location)
    else:
        location.is_deleted = True

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@locations_api_router.post("/restore")
async def api_restore_location(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    location_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    location = (
        await session.execute(
            select(LocationModel).where(
                LocationModel.id == location_id,
                LocationModel.company_id == company_id,
                LocationModel.is_deleted.is_(True),
            )
        )
    ).scalar_one_or_none()

    if not location:
        raise NotFoundError(
            detail="Расположение счетчика не найдено!"
        )

    location.is_deleted = False

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
