import io
import math
from datetime import date as date_
from typing import Optional, Literal
from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)
from fastapi.responses import StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import CustomHTTPException, check_is_none
from core.templates.jinja_filters import format_datetime_tz

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from infrastructure.db import async_db_session, async_db_session_begin

from models.enums import VerifierEquipmentAction, EmployeeStatus

from apps.company_app.repositories import (
    EquipmentRepository
)
from apps.company_app.common import validate_image, validate_pdf
from apps.company_app.schemas.equipments import (
    EquipmentsPage, EquipmentOut, EquipmentForm
)
from apps.company_app.common import log_verifier_equipment_action


equipments_api_router = APIRouter(
    prefix="/api/equipments"
)


@equipments_api_router.get("/", response_model=EquipmentsPage)
async def api_get_equipments(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    name: Optional[str] = Query(None),
    factory_number: Optional[str] = Query(None),
    inventory_number: Optional[str] = Query(None),
    register_number: Optional[str] = Query(None),
    verif_date_from: Optional[date_] = Query(None),
    verif_date_to: Optional[date_] = Query(None),
    status: Literal["all", "active", "deleted"] = Query("all"),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    repo = EquipmentRepository(session)

    only_active = status == "active"
    only_deleted = status == "deleted"

    rows, total = await repo.get_paginated(
        company_id=company_id,
        page=page,
        per_page=settings.entries_per_page,
        name=name,
        factory_number=factory_number,
        inventory_number=inventory_number,
        register_number=register_number,
        verif_date_from=verif_date_from,
        verif_date_to=verif_date_to,
        only_active=only_active,
        only_deleted=only_deleted,
    )

    total_pages = max(1, math.ceil(total / settings.entries_per_page))

    items: list[EquipmentOut] = []
    for e in rows:
        e.is_deleted = bool(e.is_deleted)
        out = EquipmentOut.model_validate(e, from_attributes=True)

        out.created_at_strftime_full = format_datetime_tz(
            e.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        out.updated_at_strftime_full = format_datetime_tz(
            e.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )

        if e.image:
            out.image_url = f"/companies/api/equipments/file?company_id={company_id}&equipment_id={e.id}&field=image"
        if e.image2:
            out.image2_url = f"/companies/api/equipments/file?company_id={company_id}&equipment_id={e.id}&field=image2"
        out.has_document = bool(e.document_pdf)

        items.append(out)

    return EquipmentsPage(items=items, page=page, total_pages=total_pages)


@equipments_api_router.post("/create")
async def api_create_equipment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_data: EquipmentForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = EquipmentRepository(session)

    if await repo.exists_with_factory_number(
            company_id, equipment_data.name, equipment_data.factory_number):
        raise CustomHTTPException(
            company_id=company_id, status_code=400,
            detail="Оборудование с таким заводским номером уже существует!")

    if await repo.exists_with_inventory_number(
            company_id, equipment_data.inventory_number):
        raise CustomHTTPException(
            company_id=company_id, status_code=400,
            detail="Оборудование с таким инвентарным номером уже существует!")

    if equipment_data.image:
        validate_image(company_id, equipment_data.image)

    if equipment_data.image2:
        validate_image(company_id, equipment_data.image2)

    if equipment_data.document_pdf:
        validate_pdf(company_id, equipment_data.document_pdf)

    await repo.create(company_id, **equipment_data.model_dump())

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@equipments_api_router.put("/update")
async def api_update_equipment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_data: EquipmentForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    repo = EquipmentRepository(session)

    if await repo.exists_with_factory_number(
            company_id, equipment_data.name, equipment_data.factory_number,
            exclude_id=equipment_id):
        raise CustomHTTPException(
            company_id=company_id, status_code=400,
            detail="Оборудование с таким заводским номером уже существует!")

    if await repo.exists_with_inventory_number(
            company_id, equipment_data.inventory_number,
            exclude_id=equipment_id):
        raise CustomHTTPException(
            company_id=company_id, status_code=400,
            detail="Оборудование с таким инвентарным номером уже существует!")

    equipment = await repo.get_by_id(
        equipment_id, company_id, only_active=False)
    await check_is_none(
        equipment, type="Оборудование", id=equipment_id, company_id=company_id)

    if equipment_data.image is not None:
        if equipment_data.image != b'':
            validate_image(company_id, equipment_data.image)
            equipment.image = equipment_data.image

    if equipment_data.image2 is not None:
        if equipment_data.image2 != b'':
            validate_image(company_id, equipment_data.image2)
            equipment.image2 = equipment_data.image2

    if equipment_data.document_pdf is not None:
        if equipment_data.document_pdf != b'':
            validate_pdf(company_id, equipment_data.document_pdf)
            equipment.document_pdf = equipment_data.document_pdf

    await repo.update(
        equipment,
        **equipment_data.model_dump(exclude={"image", "image2", "document_pdf"})
    )

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@equipments_api_router.delete("/delete")
async def delete_equipment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if user_data.status == EmployeeStatus.auditor:
        raise CustomHTTPException(
            status_code=404, detail="У вас нет доступа к этому функционалу.",
            company_id=company_id
        )

    repo = EquipmentRepository(session)

    equipment = await repo.get_by_id(
        equipment_id, company_id, with_info=True, only_active=True)

    await check_is_none(
        equipment, type="Оборудование", id=equipment_id, company_id=company_id
    )

    has_verifications = bool(equipment.verifications)
    equipment.verifiers.clear()

    if has_verifications:
        if equipment.verifiers:
            verifier = equipment.verifiers[0]
            await log_verifier_equipment_action(
                session,
                verifier_id=verifier.id,
                equipment_ids=[equipment.id],
                action=VerifierEquipmentAction.declined,
            )

        equipment.is_deleted = True
        for info in equipment.equipment_info or []:
            info.is_deleted = True
    else:
        for info in list(equipment.equipment_info or []):
            await session.delete(info)
        await session.delete(equipment)

    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@equipments_api_router.post("/restore")
async def api_restore_equipment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if user_data.status == EmployeeStatus.auditor:
        raise CustomHTTPException(
            status_code=404, detail="У вас нет доступа к этому функционалу.",
            company_id=company_id
        )

    repo = EquipmentRepository(session)

    equipment = await repo.get_by_id(
        equipment_id, company_id, only_deleted=True, with_info=True)
    await check_is_none(
        equipment, type="Оборудование", id=equipment_id, company_id=company_id
    )

    equipment.is_deleted = False
    for info in equipment.equipment_info or []:
        if hasattr(info, "is_deleted"):
            info.is_deleted = False

    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@equipments_api_router.get("/file")
async def api_get_equipment_file(
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    field: Literal["image", "image2", "document_pdf"] = Query(...),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    repo = EquipmentRepository(session)
    file_bytes = await repo.get_file(equipment_id, company_id, field)
    if not file_bytes:
        raise CustomHTTPException(
            status_code=404, detail="Файл не найден",
            company_id=company_id
        )

    media_type = "image/jpeg" if field in {
        "image", "image2"
    } else "application/pdf"

    return StreamingResponse(io.BytesIO(file_bytes), media_type=media_type)
