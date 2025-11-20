from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError


from infrastructure.db import async_db_session
from models import (
    MethodModel, SiModificationModel, RegistryNumberModel)

from access_control import (
    JwtData, check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.common import make_context


registry_numbers_frontend_router = APIRouter(
    prefix="/registry-numbers"
)


@registry_numbers_frontend_router.get("/")
async def view_registry_numbers(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
        "per_page": settings.entries_per_page
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "registry_numbers/view.html",
        context=context
    )


@registry_numbers_frontend_router.get("/create")
async def view_create_registry_number(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    methods = (
        await session.execute(
            select(MethodModel)
            .where(MethodModel.company_id == company_id)
            .order_by(MethodModel.id.asc())
        )
    ).scalars().all()
    modifications = (
        await session.execute(
            select(SiModificationModel)
            .where(SiModificationModel.company_id == company_id)
            .order_by(SiModificationModel.id.asc())
        )
    ).scalars().all()

    context = {
        "request": request,
        "modifications": modifications,
        "methods": methods,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "registry_numbers/update_or_create.html",
        context=context
    )


@registry_numbers_frontend_router.get("/update")
async def view_update_registry_number(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    registry_number = (
        await session.execute(
            select(RegistryNumberModel)
            .where(RegistryNumberModel.id == registry_number_id,
                   RegistryNumberModel.company_id == company_id)
            .options(
                selectinload(RegistryNumberModel.method),
                selectinload(RegistryNumberModel.modifications)
            )
        )
    ).scalar_one_or_none()

    if not registry_number:
        raise NotFoundError(
            company_id=company_id,
            detail="Гос.реестр не найден!"
        )

    methods = (
        await session.execute(
            select(MethodModel)
            .where(MethodModel.company_id == company_id)
            .order_by(MethodModel.id.asc())
        )
    ).scalars().all()
    modifications = (
        await session.execute(
            select(SiModificationModel)
            .where(SiModificationModel.company_id == company_id)
            .order_by(SiModificationModel.id.asc())
        )
    ).scalars().all()

    context = {
        "request": request,
        "modifications": modifications,
        "methods": methods,
        "registry_number": registry_number,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "registry_numbers/update_or_create.html",
        context=context
    )
