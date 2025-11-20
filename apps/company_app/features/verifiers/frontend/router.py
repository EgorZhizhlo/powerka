from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload, load_only
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session
from models import (
    VerifierModel, EquipmentModel)

from apps.company_app.common import make_context

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)


verifiers_frontend_router = APIRouter(
    prefix="/verifiers"
)


@verifiers_frontend_router.get("/")
async def view_verifiers(
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
        "verifiers/view.html",
        context=context
    )


@verifiers_frontend_router.get("/create")
async def view_create_verifier(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    equipments = await session.execute(
        select(EquipmentModel)
        .where(
            EquipmentModel.company_id == company_id,
            ~EquipmentModel.verifiers.any())
        .order_by(EquipmentModel.inventory_number)
        .options(
            load_only(
                EquipmentModel.id,
                EquipmentModel.name,
                EquipmentModel.factory_number,
                EquipmentModel.inventory_number
            )
        )
    )
    equipments = equipments.scalars().all()

    context = {
        "request": request,
        "equipments": equipments,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "verifiers/update_or_create.html",
        context=context
    )


@verifiers_frontend_router.get("/update")
async def view_update_verifier(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verifier_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    verifier = (
        await session.execute(
            select(VerifierModel)
            .where(
                VerifierModel.id == verifier_id,
                VerifierModel.company_id == company_id
            )
            .options(
                selectinload(VerifierModel.equipments)
                .load_only(
                    EquipmentModel.id,
                    EquipmentModel.name,
                    EquipmentModel.factory_number,
                    EquipmentModel.inventory_number
                )
            )
        )
    ).scalar_one_or_none()

    if not verifier:
        raise NotFoundError(
            company_id=company_id,
            detail="Поверитель не найден!"
        )

    equipments = await session.execute(
        select(EquipmentModel)
        .where(
            or_(
                EquipmentModel.verifiers.any(VerifierModel.id == verifier_id),
                ~EquipmentModel.verifiers.any()
            ),
            EquipmentModel.company_id == company_id)
        .order_by(EquipmentModel.inventory_number)
        .options(
            load_only(
                EquipmentModel.id,
                EquipmentModel.name,
                EquipmentModel.factory_number,
                EquipmentModel.inventory_number
            )
        )
    )
    equipments = equipments.scalars().all()

    context = {
        "request": request,
        "verifier": verifier,
        "equipments": equipments,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "verifiers/update_or_create.html",
        context=context
    )
