import math
from fastapi import (
    APIRouter, Response, status as status_code,
    Query, Depends, Body
)

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from models import SiModificationModel

from apps.company_app.schemas.si_modifications import (
    SiModificationCreate, ModificationsPage, SiModificationOut
)

si_modifications_api_router = APIRouter(
    prefix="/api/si-modifications"
)


@si_modifications_api_router.get(
    "/", response_model=ModificationsPage)
async def api_get_modifications(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    session: AsyncSession = Depends(async_db_session),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
):
    per_page = settings.entries_per_page
    clause = SiModificationModel.modification_name.ilike(f"%{search}%")

    total = (
        await session.scalar(
            select(func.count(SiModificationModel.id)).where(
                SiModificationModel.company_id == company_id, clause
            )
        )
    )
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    mods = (
        await session.scalars(
            select(SiModificationModel)
            .where(SiModificationModel.company_id == company_id, clause)
            .order_by(
                SiModificationModel.is_deleted.isnot(True).desc(),
                SiModificationModel.id.desc())
            .limit(per_page).offset(offset)
        )
    ).all()

    items = []
    for obj in mods:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = SiModificationOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(SiModificationOut(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@si_modifications_api_router.post("/create")
async def api_create_modification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    modification_data: SiModificationCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_modification = SiModificationModel(
        modification_name=modification_data.modification_name,
        company_id=company_id
    )
    session.add(new_modification)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@si_modifications_api_router.put("/update")
async def api_update_modification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    modification_id: int = Query(..., ge=1, le=settings.max_int),
    modification_data: SiModificationCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    modification = (await session.execute(
        select(SiModificationModel)
        .where(
            SiModificationModel.company_id == company_id,
            SiModificationModel.id == modification_id
        )
    )).scalar_one_or_none()

    await check_is_none(
        modification, type="Модификация СИ", id=modification_id,
        company_id=company_id)

    modification.modification_name = modification_data.modification_name

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@si_modifications_api_router.delete("/delete")
async def api_delete_modification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    modification_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    mod = (
        await session.scalar(
            select(SiModificationModel)
            .where(
                SiModificationModel.id == modification_id,
                SiModificationModel.company_id == company_id,
                SiModificationModel.is_deleted.is_(False),
            )
            .options(
                selectinload(SiModificationModel.verifications),
                selectinload(SiModificationModel.registry_numbers)
            )
        )
    )
    await check_is_none(
        result=mod,
        type="Модификация СИ",
        id=modification_id,
        company_id=company_id
    )

    has_verifs = bool(mod.verifications)

    mod.registry_numbers.clear()

    if has_verifs:
        mod.is_deleted = True
    else:
        await session.flush()
        await session.delete(mod)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@si_modifications_api_router.post("/restore")
async def api_restore_modification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    modification_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    mod = await session.scalar(
        select(SiModificationModel)
        .where(
            SiModificationModel.id == modification_id,
            SiModificationModel.company_id == company_id,
            SiModificationModel.is_deleted.is_(True),
        )
    )
    await check_is_none(
        result=mod,
        type="Модификация СИ",
        id=modification_id,
        company_id=company_id
    )

    mod.is_deleted = False
    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
