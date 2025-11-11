from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from models import MethodModel, RegistryNumberModel

from apps.company_app.schemas.methods import (
    MethodsPage, MethodForm, MethodOut
)


methods_api_router = APIRouter(
    prefix="/api/methods"
)


@methods_api_router.get(
    "/",
    response_model=MethodsPage,
)
async def api_get_methods(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    search_clause = MethodModel.name.ilike(f"%{search}%")

    total = (
        await session.execute(
            select(func.count(MethodModel.id)).where(
                MethodModel.company_id == company_id,
                search_clause,
            )
        )
    ).scalar_one()

    import math
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    stmt = (
        select(MethodModel)
        .where(
            MethodModel.company_id == company_id,
            search_clause,
        )
        .order_by(
            MethodModel.is_deleted.isnot(True).desc(),
            MethodModel.id.desc(),
        )
        .limit(per_page)
        .offset(offset)
    )

    result = await session.execute(stmt)
    objs = result.scalars().all()

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = MethodOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(MethodOut(**item_dict))

    return {
        "items": items,
        "page": page,
        "total_pages": total_pages,
    }


@methods_api_router.post("/create")
async def api_create_method(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    method_data: MethodForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_method = MethodModel(
        name=method_data.name,
        company_id=company_id
    )
    session.add(new_method)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@methods_api_router.put("/update")
async def api_update_method(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    method_id: int = Query(..., ge=1, le=settings.max_int),
    method_data: MethodForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    method = (await session.execute(
        select(MethodModel)
        .where(
            MethodModel.company_id == company_id,
            MethodModel.id == method_id
        )
    )).scalar_one_or_none()

    await check_is_none(
        method, type="Методика", id=method_id, company_id=company_id)

    method.name = method_data.name

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@methods_api_router.delete("/delete")
async def api_delete_method(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    method_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    method: MethodModel | None = (await session.execute(
        select(MethodModel)
        .where(MethodModel.id == method_id,
               MethodModel.company_id == company_id,
               MethodModel.is_deleted.isnot(True))
        .options(
            selectinload(MethodModel.registry_numbers)
            .selectinload(RegistryNumberModel.verifications),
            selectinload(MethodModel.verifications)
        )
    )).scalar_one_or_none()

    await check_is_none(
        method, type="Методика", id=method_id, company_id=company_id)

    # Есть ли хоть одна поверка у методики ИЛИ у любого гос-реестра?
    has_verifs = bool(method.verifications) or any(
        rn.verifications for rn in method.registry_numbers
    )

    if has_verifs:
        # мягкое удаление/блокировка
        method.is_deleted = True
        for rn in method.registry_numbers:
            rn.is_deleted = True
    else:
        # жёстко: сперва удаляем реестры, затем методику
        for rn in list(method.registry_numbers):
            await session.delete(rn)
        await session.flush()
        await session.delete(method)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@methods_api_router.post("/restore")
async def api_restore_method(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    method_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    method = (await session.execute(
        select(MethodModel)
        .where(MethodModel.id == method_id,
               MethodModel.company_id == company_id,
               MethodModel.is_deleted.is_(True))
        .options(selectinload(MethodModel.registry_numbers))
    )).scalar_one_or_none()

    await check_is_none(
        method, type="Методика", id=method_id, company_id=company_id)

    method.is_deleted = False
    for rn in method.registry_numbers:
        rn.is_deleted = False

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
