import math
from fastapi import (
    APIRouter, Request, status as status_code, Response,
    Depends, Query, Body
)

from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import (
    NotFoundError, ForbiddenError, ConflictError
)

from infrastructure.db import async_db_session, async_db_session_begin
from models.enums import (
    VerifierEquipmentAction, EquipmentType, EmployeeStatus
)
from models import (
    VerifierModel, EquipmentModel
)
from models.associations import equipments_verifiers

from apps.company_app.schemas.verifiers import (
    VerifiersPage, VerifierForm, VerifierOut
)

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from apps.company_app.common import log_verifier_equipment_action


verifiers_api_router = APIRouter(
    prefix="/api/verifiers"
)


@verifiers_api_router.get(
    "/",
    response_model=VerifiersPage
)
async def api_get_verifiers(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    search_clause = (
        VerifierModel.last_name.ilike(f"%{search}%")
        | VerifierModel.name.ilike(f"%{search}%")
        | VerifierModel.patronymic.ilike(f"%{search}%")
        | VerifierModel.snils.ilike(f"%{search}%")
    )

    total = (
        await session.execute(
            select(func.count(VerifierModel.id))
            .where(VerifierModel.company_id == company_id, search_clause)
        )
    ).scalar_one()
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    q = (
        select(VerifierModel)
        .options(
            selectinload(VerifierModel.equipments)
            .load_only(
                EquipmentModel.id,
                EquipmentModel.name,
                EquipmentModel.factory_number,
                EquipmentModel.inventory_number
            )
        )
        .where(
            VerifierModel.company_id == company_id, search_clause)
        .order_by(
            VerifierModel.is_deleted.isnot(True).desc(),  # False / NULL → выше
            VerifierModel.id.desc()
        )
        .limit(per_page)
        .offset(offset)
    )
    objs = (await session.execute(q)).scalars().all()

    items = []
    for obj in objs:
        obj.is_deleted = bool(obj.is_deleted)
        obj.equipments.sort(key=lambda e: e.inventory_number)
        item_dict = VerifierOut.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(VerifierOut(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@verifiers_api_router.post("/create")
async def api_create_verifier(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_data: VerifierForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_verifier = VerifierModel(company_id=company_id)
    for field, value in verifier_data.model_dump().items():
        if field != "equipments":
            setattr(new_verifier, field, value)

    if verifier_data.equipments:
        result = await session.execute(
            select(EquipmentModel).where(
                EquipmentModel.id.in_(verifier_data.equipments)
            )
        )
        selected = result.scalars().all()

        etalon_count = sum(
            1 for eq in selected if eq.type.lower() == EquipmentType.standard)
        if etalon_count > 1:
            raise ConflictError(
                detail=(
                    "Поверитель может использовать не более 1 средства"
                    " измерений, используемое в качестве эталона!"
                )
            )

        await session.execute(
            delete(equipments_verifiers).where(
                equipments_verifiers.c.equipment_id.in_(
                    verifier_data.equipments),
                equipments_verifiers.c.verifier_id.is_(None)
            )
        )

        new_verifier.equipments = selected

    session.add(new_verifier)
    await session.flush()

    await log_verifier_equipment_action(
        session,
        verifier_id=new_verifier.id,
        equipment_ids=[eq.id for eq in verifier_data.equipments],
        action=VerifierEquipmentAction.accepted,
    )

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@verifiers_api_router.put("/update")
async def api_update_verifier(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_data: VerifierForm = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    verifier = (await session.execute(
        select(VerifierModel)
        .options(selectinload(VerifierModel.equipments))
        .where(
            VerifierModel.company_id == company_id,
            VerifierModel.id == verifier_id
        )
    )).scalar_one_or_none()

    if not verifier:
        raise NotFoundError(
            company_id=company_id,
            detail="Поверитель не найден!"
        )

    updated = verifier_data.model_dump(exclude_unset=True)

    if "equipments" in updated:
        new_equipment_ids = set(updated["equipments"])
        old_equipment_ids = {eq.id for eq in verifier.equipments}

        added_ids = list(new_equipment_ids - old_equipment_ids)
        removed_ids = list(old_equipment_ids - new_equipment_ids)

        result = await session.execute(
            select(EquipmentModel).where(
                EquipmentModel.id.in_(updated["equipments"])
            )
        )
        selected = result.scalars().all()

        etalon_count = sum(
            1 for eq in selected if eq.type.lower() == EquipmentType.standard)
        if etalon_count > 1:
            raise ConflictError(
                detail=(
                    "Поверитель может использовать не более 1 средства"
                    " измерений, используемое в качестве эталона!"
                )
            )

        # отвязываем эти приборы от всех остальных верификаторов
        await session.execute(
            delete(equipments_verifiers).where(
                equipments_verifiers.c.equipment_id.in_(
                    updated["equipments"]),
                equipments_verifiers.c.verifier_id != verifier_id
            )
        )

        # привязываем их к текущему
        verifier.equipments = selected

        if added_ids:
            await log_verifier_equipment_action(
                session,
                verifier_id=verifier_id,
                equipment_ids=added_ids,
                action=VerifierEquipmentAction.accepted,
            )
        if removed_ids:
            await log_verifier_equipment_action(
                session,
                verifier_id=verifier_id,
                equipment_ids=removed_ids,
                action=VerifierEquipmentAction.declined,
            )

    # остальные поля
    for field, value in updated.items():
        if field != "equipments":
            setattr(verifier, field, value)

    session.add(verifier)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@verifiers_api_router.delete("/delete")
async def api_delete_verifier(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if user_data.status == EmployeeStatus.auditor:
        raise ForbiddenError(
            detail="У вас нет доступа к этому функционалу!"
        )

    # загружаем поверителя с зависимыми связями
    q = (
        select(VerifierModel)
        .options(
            selectinload(VerifierModel.verification),
            selectinload(VerifierModel.equipments),
            selectinload(VerifierModel.employees),
            selectinload(VerifierModel.verification_logs),
        )
        .where(
            VerifierModel.id == verifier_id,
            VerifierModel.company_id == company_id,
        )
    )
    verifier = (await session.execute(q)).scalar_one_or_none()

    if not verifier:
        raise NotFoundError(
            company_id=company_id,
            detail="Поверитель не найден!"
        )

    if not verifier.verification:
        verifier.equipments.clear()
        for emp in verifier.employees:
            emp.default_verifier = None
        await session.delete(verifier)
    else:
        if verifier.equipments:
            await log_verifier_equipment_action(
                session,
                verifier_id=verifier.id,
                equipment_ids=[eq.id for eq in verifier.equipments],
                action=VerifierEquipmentAction.declined,
            )
        verifier.equipments.clear()
        for emp in verifier.employees:
            emp.default_verifier = None
        verifier.is_deleted = True

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@verifiers_api_router.post("/restore")
async def api_restore_verifier(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if user_data.status == EmployeeStatus.auditor:
        raise ForbiddenError(
            detail="У вас нет доступа к этому функционалу!"
        )

    q = select(VerifierModel).where(
        VerifierModel.id == verifier_id,
        VerifierModel.company_id == company_id,
        VerifierModel.is_deleted.is_(True),
    )
    verifier = (await session.execute(q)).scalar_one_or_none()

    if not verifier:
        raise NotFoundError(
            company_id=company_id,
            detail="Поверитель не найден!"
        )

    verifier.is_deleted = False

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
