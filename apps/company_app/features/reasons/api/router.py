from fastapi import (
    APIRouter, Response, status as status_code,
    Query, Depends, Body
)

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import NotFoundError

from infrastructure.db import async_db_session, async_db_session_begin
from models import ReasonModel

from apps.company_app.schemas.reasons import (
    ReasonsPage, ReasonForm, ReasonOut
)


reasons_api_router = APIRouter(
    prefix="/api/reasons"
)


@reasons_api_router.get(
    "/",
    response_model=ReasonsPage,
)
async def api_get_reasons(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page
    clause = (
        ReasonModel.name.ilike(f"%{search}%")
        | ReasonModel.full_name.ilike(f"%{search}%"))

    total = (
        await session.execute(
            select(func.count(ReasonModel.id))
            .where(ReasonModel.company_id == company_id, clause)
        )
    ).scalar_one()

    import math
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    q = (
        select(ReasonModel)
        .where(ReasonModel.company_id == company_id, clause)
        .order_by(
            ReasonModel.is_deleted.isnot(True).desc(),
            ReasonModel.id.desc()
        )
        .limit(per_page).offset(offset)
    )
    objs = (await session.execute(q)).scalars().all()

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = ReasonOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(ReasonOut(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@reasons_api_router.post("/create")
async def api_create_reason(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    reason_data: ReasonForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_reason = ReasonModel()

    for field, value in reason_data.model_dump().items():
        setattr(new_reason, field, value)

    new_reason.company_id = company_id

    session.add(new_reason)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@reasons_api_router.put("/update")
async def api_update_reason(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    reason_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    reason_data: ReasonForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    reason = (
        await session.execute(
            select(ReasonModel)
            .where(
                ReasonModel.company_id == company_id,
                ReasonModel.id == reason_id
            )
        )
    ).scalar_one_or_none()

    if not reason:
        raise NotFoundError(
            detail="Причина непригодности не найдена!"
        )

    for field, value in reason_data.model_dump().items():
        setattr(reason, field, value)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@reasons_api_router.delete("/delete")
async def api_delete_reason(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    reason_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    reason = (
        await session.execute(
            select(ReasonModel)
            .where(
                ReasonModel.id == reason_id,
                ReasonModel.company_id == company_id,
                ReasonModel.is_deleted.isnot(True),
            )
            .options(selectinload(ReasonModel.verifications))
        )
    ).scalar_one_or_none()

    if not reason:
        raise NotFoundError(
            detail="Причина непригодности не найдена!"
        )

    can_hard_delete = not reason.verifications
    if can_hard_delete:
        await session.delete(reason)
    else:
        reason.is_deleted = True

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@reasons_api_router.post("/restore")
async def api_restore_reason(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    reason_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    reason = (
        await session.execute(
            select(ReasonModel).where(
                ReasonModel.id == reason_id,
                ReasonModel.company_id == company_id,
                ReasonModel.is_deleted.is_(True),
            )
        )
    ).scalar_one_or_none()

    if not reason:
        raise NotFoundError(
            detail="Причина непригодности не найдена!"
        )

    reason.is_deleted = False
    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
