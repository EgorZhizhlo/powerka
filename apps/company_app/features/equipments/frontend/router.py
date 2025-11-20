from types import SimpleNamespace

from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import (
    NotFoundError
)

from infrastructure.db import async_db_session
from models import CompanyModel

from apps.company_app.repositories import (
    EquipmentRepository, CompanyActivityRepository,
    CompanySiTypeRepository
)

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)
from apps.company_app.schemas.equipments import EquipmentOut

from apps.company_app.common import make_context


equipments_frontend_router = APIRouter(
    prefix="/equipments"
)


@equipments_frontend_router.get("/")
async def view_equipments(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
        "per_page": settings.entries_per_page
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "equipments/view.html",
        context=context
    )


@equipments_frontend_router.get("/create")
async def view_create_equipment(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    activity_repo = CompanyActivityRepository(session=session)
    si_type_repo = CompanySiTypeRepository(session=session)

    activities = await activity_repo.get_activities_in_company(
        company_id=company_id
    )
    si_types = await si_type_repo.get_si_types_in_company(
        company_id=company_id
    )
    workplace = (await session.execute(
        select(CompanyModel.workplace)
        .where(CompanyModel.id == company_id)
    )
    ).scalar_one_or_none()

    context = {
        "place": workplace,
        "view_type": "create",
        "request": request,
        "activities": activities,
        "si_types": si_types,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "equipments/update_or_create.html",
        context=context
    )


@equipments_frontend_router.get("/copy")
async def view_copy_equipment(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    activity_repo = CompanyActivityRepository(session)
    si_type_repo = CompanySiTypeRepository(session)
    equipment_repo = EquipmentRepository(session)

    activities = await activity_repo.get_activities_in_company(company_id)
    si_types = await si_type_repo.get_si_types_in_company(company_id)

    equipment = await equipment_repo.get_by_id(
        equipment_id, company_id, only_active=True
    )
    if not equipment:
        raise NotFoundError(
            company_id=company_id,
            detail="Оборудование не найдено!"
        )

    equipment_copy = SimpleNamespace(
        id=None,
        name=equipment.name,
        full_name=equipment.full_name,
        factory_number=None,
        inventory_number=None,
        type=equipment.type,
        register_number=equipment.register_number,
        list_number=None,
        year_of_issue=equipment.year_of_issue,
        measurement_range=equipment.measurement_range,
        error_or_uncertainty=equipment.error_or_uncertainty,
        software_identifier=equipment.software_identifier,
        is_opt=equipment.is_opt,
        activity_id=equipment.activity_id,
        si_type_id=equipment.si_type_id,
        manufacturer_country=equipment.manufacturer_country,
        manufacturer_name=equipment.manufacturer_name,
        commissioning_year=equipment.commissioning_year,
        ownership_document=equipment.ownership_document,
        storage_place=equipment.storage_place
    )

    workplace = (await session.execute(
        select(CompanyModel.workplace)
        .where(CompanyModel.id == company_id)
    )
    ).scalar_one_or_none()

    context = {
        "request": request,
        "place": workplace,
        "equipment": equipment_copy,
        "activities": activities,
        "si_types": si_types,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "equipments/update_or_create.html",
        context=context
    )


@equipments_frontend_router.get("/update")
async def view_update_equipment(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    activity_repo = CompanyActivityRepository(session=session)
    si_type_repo = CompanySiTypeRepository(session=session)
    equipment_repo = EquipmentRepository(session=session)

    activities = await activity_repo.get_activities_in_company(
        company_id=company_id
    )

    si_types = await si_type_repo.get_si_types_in_company(
        company_id=company_id
    )

    equipment = await equipment_repo.get_by_id(
        equipment_id=equipment_id,
        company_id=company_id,
        only_active=True
    )
    if not equipment:
        raise NotFoundError(
            company_id=company_id,
            detail="Оборудование не найдено!"
        )

    val_equipment = EquipmentOut.model_validate(equipment)

    workplace = (await session.execute(
        select(CompanyModel.workplace)
        .where(CompanyModel.id == company_id)
    )).scalar_one_or_none()

    context = {
        "place": workplace,
        "request": request,
        "equipment": val_equipment,
        "view_type": "update",
        "activities": activities,
        "si_types": si_types,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "equipments/update_or_create.html",
        context=context
    )
