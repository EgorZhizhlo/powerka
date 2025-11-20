from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session

from models import EquipmentModel, EquipmentInfoModel
from models.enums.equipment_info import EquipmentInfoType

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.common import make_context


equipment_informations_frontend_router = APIRouter(
    prefix="/equipment-informations"
)


@equipment_informations_frontend_router.get("/")
async def view_equipment_informations(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    equipment = (
        await session.execute(
            select(EquipmentModel)
            .where(
                EquipmentModel.id == equipment_id,
                EquipmentModel.company_id == company_id)
            .options(
                selectinload(EquipmentModel.equipment_info)
            )
        )
    ).scalar_one_or_none()

    if not equipment:
        raise NotFoundError(
            company_id=company_id,
            detail="Оборудование не найдено!"
        )

    context = {
        "request": request,
        "equipment": equipment
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "equipment_informations/view.html",
        context=context
    )


@equipment_informations_frontend_router.get(
    "/create")
async def view_create_equipment_information(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    type_verif: EquipmentInfoType = Query(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):

    context = {
        "request": request,
        "view_type": "create",
        "type_verif": type_verif,
        "equipment_id": equipment_id,
    }
    context.update(await make_context(session, user_data, company_id))

    template_name = (
        "equipment_informations/update_or_create_m.html"
        if type_verif == EquipmentInfoType.maintenance
        else "equipment_informations/update_or_create_v.html"
    )

    return templates.company.TemplateResponse(
        template_name,
        context=context
    )


@equipment_informations_frontend_router.get("/update")
async def view_update_equipment_information(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    type_verif: EquipmentInfoType = Query(...),
    equipment_info_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    equipment_info = (
        await session.execute(
            select(EquipmentInfoModel)
            .join(EquipmentInfoModel.equipment)
            .where(
                EquipmentInfoModel.id == equipment_info_id,
                EquipmentModel.id == equipment_id,
                EquipmentModel.company_id == company_id
            )
        )
    ).scalar_one_or_none()

    if not equipment_info:
        raise NotFoundError(
            company_id=company_id,
            detail="ТО и Поверка оборудования не найдена!"
        )

    context = {
        "request": request,
        "equipment_info": equipment_info,
        "view_type": "update",
        "equipment_id": equipment_id,
        "type_verif": type_verif,
    }
    context.update(await make_context(session, user_data, company_id))

    template_name = (
        "equipment_informations/update_or_create_m.html"
        if type_verif == EquipmentInfoType.maintenance
        else "equipment_informations/update_or_create_v.html"
    )

    return templates.company.TemplateResponse(
        template_name,
        context=context
    )
