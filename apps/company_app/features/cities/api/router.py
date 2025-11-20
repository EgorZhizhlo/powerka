from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import (
    NotFoundError, ConflictError
)

from infrastructure.db import async_db_session, async_db_session_begin

from apps.company_app.schemas.cities import (
    CityForm, CitiesPage, CityOut
)

from apps.company_app.repositories import CityRepository


cities_api_router = APIRouter(
    prefix="/api/cities"
)


@cities_api_router.get("/", response_model=CitiesPage)
async def api_get_cities(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    city_repo = CityRepository(session)
    per_page = settings.entries_per_page
    objs, page, total_pages = await city_repo.get_paginated(
        company_id=company_id,
        page=page,
        per_page=per_page,
        search=search
    )

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = CityOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(CityOut(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@cities_api_router.post("/create")
async def api_create_city(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    city_data: CityForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    city_repo = CityRepository(session)

    if await city_repo.exists_duplicate(city_data.name, company_id):
        raise ConflictError(
            detail=f"Город {city_data.name} уже был создан ранее!"
        )

    await city_repo.create(company_id, city_data.name)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@cities_api_router.put("/update")
async def api_update_city(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    city_id: int = Query(..., ge=1, le=settings.max_int),
    city_data: CityForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    city_repo = CityRepository(session)

    if await city_repo.exists_duplicate(
            name=city_data.name, company_id=company_id,
            exclude_id=city_id):
        raise ConflictError(
            detail=f"Город {city_data.name} уже был создан ранее!"
        )

    city = await city_repo.get_by_id(city_id, company_id)

    if not city:
        raise NotFoundError(
            detail="Населённый пункт не найден!"
        )

    await city_repo.update(city, city_data.name)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@cities_api_router.delete("/delete")
async def api_delete_city(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    city_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    city_repo = CityRepository(session)
    city = await city_repo.get_full_for_delete(city_id, company_id)

    if not city:
        raise NotFoundError(
            detail="Населённый пункт не найден!"
        )

    await city_repo.delete(city)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@cities_api_router.post("/restore")
async def api_restore_city(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    city_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    city_repo = CityRepository(session)
    city = await city_repo.get_full_for_restore(city_id, company_id)

    if not city:
        raise NotFoundError(
            detail="Населённый пункт не найден!"
        )

    await city_repo.restore(city)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
