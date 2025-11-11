import math
from fastapi import (
    APIRouter, HTTPException, Response, status as status_code,
    Depends, Query, Body)

from sqlalchemy import select, delete, func, cast, String
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import check_is_none
from core.templates.jinja_filters import format_datetime_tz

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from infrastructure.db import async_db_session, async_db_session_begin
from models import SiModificationModel, RegistryNumberModel
from models.associations import (
    registry_numbers_modifications
)

from apps.company_app.schemas.registry_numbers import (
    RegistryNumberCreate, RegistryNumberPage, RegistryNumberOut
)


registry_numbers_api_router = APIRouter(
    prefix="/api/registry-numbers"
)


@registry_numbers_api_router.get(
    "/", response_model=RegistryNumberPage
)
async def api_get_registry_numbers(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    session: AsyncSession = Depends(async_db_session),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
):
    per_page = settings.entries_per_page
    clause = (
        RegistryNumberModel.registry_number.ilike(f"%{search}%")
        | RegistryNumberModel.si_type.ilike(f"%{search}%")
        | cast(RegistryNumberModel.mpi_hot, String).ilike(f"%{search}%")
        | cast(RegistryNumberModel.mpi_cold, String).ilike(f"%{search}%")
    )

    total = await session.scalar(
        select(func.count(RegistryNumberModel.id))
        .where(RegistryNumberModel.company_id == company_id, clause)
    )
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    q = (
        select(RegistryNumberModel)
        .where(RegistryNumberModel.company_id == company_id, clause)
        .options(
            selectinload(RegistryNumberModel.method),
            selectinload(RegistryNumberModel.modifications)
        )
        .order_by(
            RegistryNumberModel.is_deleted.isnot(True).desc(),
            RegistryNumberModel.id.desc()
        )
        .limit(per_page)
        .offset(offset)
    )
    objs = (await session.execute(q)).scalars().all()

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        item_dict = RegistryNumberOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(RegistryNumberOut(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@registry_numbers_api_router.post("/create")
async def api_create_registry_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_data: RegistryNumberCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_registry_number = RegistryNumberModel(
        company_id=company_id
    )
    for field, value in registry_number_data.model_dump().items():
        if field not in {"modifications"}:
            setattr(new_registry_number, field, value)

    if registry_number_data.modifications:
        modifications_objects = await session.execute(
            select(SiModificationModel).where(
                SiModificationModel.id.in_(registry_number_data.modifications))
        )
        new_registry_number.modifications.extend(
            modifications_objects.scalars().all())

    session.add(new_registry_number)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@registry_numbers_api_router.put("/update")
async def api_update_registry_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_data: RegistryNumberCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    registry_number = (
        await session.execute(
            select(RegistryNumberModel)
            .where(RegistryNumberModel.company_id == company_id,
                   RegistryNumberModel.id == registry_number_id)
            .options(
                selectinload(RegistryNumberModel.method),
                selectinload(RegistryNumberModel.modifications))
        )
    ).scalar_one_or_none()
    await check_is_none(
        registry_number, type="Гос.реестр", id=registry_number_id, company_id=company_id)

    for field, value in registry_number_data.model_dump().items():
        if field not in {"modifications"}:
            setattr(registry_number, field, value)

    await session.execute(
        delete(registry_numbers_modifications)
        .where(
            registry_numbers_modifications.c.registry_id == registry_number.id
        )
    )

    modifications_objects = await session.execute(
        select(SiModificationModel).where(
            SiModificationModel.id.in_(registry_number_data.modifications))
    )
    modifications = modifications_objects.scalars().all()
    registry_number.modifications.extend(modifications)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@registry_numbers_api_router.delete(
    "/delete", status_code=status_code.HTTP_204_NO_CONTENT,
    responses={
        status_code.HTTP_404_NOT_FOUND: {
            "description": "Номер госреестра не найден"
        }
    },
)
async def api_delete_registry_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    registry = await session.get(
        RegistryNumberModel, registry_number_id,
        options=[
            selectinload(RegistryNumberModel.verifications),
            selectinload(RegistryNumberModel.modifications)
        ]
    )
    if not registry or registry.company_id != company_id or registry.is_deleted:
        raise HTTPException(
            status_code.HTTP_404_NOT_FOUND,
            "Номер госреестра не найден")

    # разрываем связи с модификациями
    registry.modifications.clear()
    has_verifs = bool(registry.verifications)

    if has_verifs:
        registry.is_deleted = True
    else:
        await session.delete(registry)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@registry_numbers_api_router.post(
    "/restore", status_code=status_code.HTTP_200_OK,
    responses={
        status_code.HTTP_404_NOT_FOUND: {
            "description": "Удалённый номер госреестра не найден"
        }
    },
)
async def api_restore_registry_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    registry = await session.get(
        RegistryNumberModel, registry_number_id,
        options=[selectinload(RegistryNumberModel.method)]
    )
    if not registry or registry.company_id != company_id or not registry.is_deleted:
        raise HTTPException(404, "Удалённый номер госреестра не найден")

    if registry.method and registry.method.is_deleted:
        raise HTTPException(
            status_code.HTTP_400_BAD_REQUEST,
            "Номер госреестра невозможно восстановить, "
            "так как связанная методика помечена как удалённая. "
            "Сначала восстановите методику."
        )

    registry.is_deleted = False
    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
