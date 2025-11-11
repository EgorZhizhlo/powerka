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

from infrastructure.db import async_db_session, async_db_session_begin

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import check_is_none, CustomHTTPException
from core.templates.jinja_filters import format_datetime_tz

from apps.company_app.schemas.act_numbers import (
    ActNumberForm, ActNumbersPage, ActNumberOut
)

from apps.company_app.repositories import ActNumberRepository


act_numbers_api_router = APIRouter(
    prefix="/api/act-numbers"
)


@act_numbers_api_router.get(
    "/",
    response_model=ActNumbersPage
)
async def api_get_act_numbers(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    act_numbers_repo = ActNumberRepository(session)
    per_page = settings.entries_per_page

    objs, page, total_pages = await act_numbers_repo.get_paginated(
        company_id=company_id,
        page=page,
        per_page=per_page,
        search=search
    )

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = ActNumberOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )

        items.append(ActNumberOut(**item_dict))

    return {
        "items": items,
        "page": page,
        "total_pages": total_pages,
    }


@act_numbers_api_router.post("/create")
async def api_create_act_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    act_number_data: ActNumberForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActNumberRepository(session)

    if await repo.exists_duplicate(
        act_number=act_number_data.act_number,
        series_id=act_number_data.series_id,
        company_id=company_id,
    ):
        raise CustomHTTPException(
            company_id=company_id,
            status_code=status_code.HTTP_400_BAD_REQUEST,
            detail=f"Номер акта {act_number_data.act_number} уже существует!"
        )

    await repo.create(company_id, **act_number_data.model_dump())

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_numbers_api_router.put("/update")
async def api_update_act_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_number_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    act_number_data: ActNumberForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActNumberRepository(session)

    if await repo.exists_duplicate(
        act_number=act_number_data.act_number,
        series_id=act_number_data.series_id,
        company_id=company_id,
        exclude_id=act_number_id,
    ):
        raise CustomHTTPException(
            company_id=company_id,
            status_code=status_code.HTTP_400_BAD_REQUEST,
            detail=f"Номер акта {act_number_data.act_number} уже существует!"
        )

    act_number_entry = await repo.get_by_id(
        act_number_id, company_id)
    await check_is_none(
        act_number_entry, type="Номер акта",
        id=act_number_id, company_id=company_id
    )

    await repo.update(
        act_number_entry, **act_number_data.model_dump()
    )

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_numbers_api_router.delete("/delete")
async def api_delete_act_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_number_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActNumberRepository(session)

    act_number = await repo.get_by_id(act_number_id, company_id)
    await check_is_none(
        act_number, type="Номер бланка",
        id=act_number_id, company_id=company_id
    )

    await repo.delete_or_soft_delete(act_number)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@act_numbers_api_router.post("/restore")
async def api_restore_act_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_number_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = ActNumberRepository(session)

    act_number = await repo.restore(act_number_id, company_id)
    await check_is_none(
        act_number, type="Номер бланка",
        id=act_number_id, company_id=company_id
    )

    if act_number.series and act_number.series.is_deleted:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Номер акта невозможно восстановить, "
                   "так как его серия помечена как удалённая. "
                   "Сначала восстановите серию.",
        )

    if act_number.city and act_number.city.is_deleted:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Номер акта невозможно восстановить, "
                   "так как связанный населённый пункт помечен как удалённый. "
                   "Сначала восстановите населённый пункт.",
        )

    act_number.is_deleted = False

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
