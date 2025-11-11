from fastapi import (
    APIRouter, Response, status as status_code,
    Query, Depends, Body
)

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from core.db.dependencies import get_company_timezone

from apps.company_app.schemas.act_series import (
    ActSeriesPage, ActSeriesForm, ActSeriesOut
)
from apps.company_app.repositories import ActSeriesRepository


act_series_api_router = APIRouter(
    prefix="/api/act-series"
)


@act_series_api_router.get("/", response_model=ActSeriesPage)
async def api_get_act_series(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    repo = ActSeriesRepository(session)
    per_page = settings.entries_per_page

    objs, page, total_pages = await repo.get_paginated(
        company_id=company_id,
        page=page,
        per_page=per_page,
        search=search
    )

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = ActSeriesOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(ActSeriesOut(**item_dict))

    return {
        "items": items,
        "page": page,
        "total_pages": total_pages,
    }


@act_series_api_router.post("/create")
async def api_create_act_series(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    actseries_data: ActSeriesForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActSeriesRepository(session)
    await repo.create(company_id, actseries_data.name)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_series_api_router.put("/update")
async def api_update_act_series(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_series_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    actseries_data: ActSeriesForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActSeriesRepository(session)
    act_series = await repo.get_by_id(act_series_id, company_id)

    await check_is_none(
        act_series, type="Серия акта",
        id=act_series_id, company_id=company_id
    )

    await repo.update(act_series, actseries_data.name)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_series_api_router.delete("/delete")
async def api_delete_act_series(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_series_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActSeriesRepository(session)
    series = await repo.get_full_for_delete(act_series_id, company_id)
    await check_is_none(
        series, type="Серия бланка",
        id=act_series_id, company_id=company_id
    )

    await repo.delete_or_soft_delete(series)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_series_api_router.post("/restore")
async def api_restore_act_series(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_series_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActSeriesRepository(session)
    series = await repo.restore(act_series_id, company_id)
    await check_is_none(
        series, type="Серия бланка",
        id=act_series_id, company_id=company_id
    )

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
