from fastapi import APIRouter, Request, Query, Depends

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session
from models import SiModificationModel

from access_control import (
    JwtData, check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.common import make_context

si_modifications_frontend_router = APIRouter(
    prefix="/si-modifications"
)


@si_modifications_frontend_router.get("/")
async def view_si_modifications(
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
        "si_modifications/view.html",
        context=context
    )


@si_modifications_frontend_router.get("/create")
async def view_create_modification(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "si_modifications/update_or_create.html",
        context=context
    )


@si_modifications_frontend_router.get("/update")
async def view_update_modification(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    modification_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    modification = (
        await session.execute(
            select(SiModificationModel)
            .where(
                SiModificationModel.id == modification_id,
                SiModificationModel.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    if not modification:
        raise NotFoundError(
            company_id=company_id,
            detail="Модификация СИ не найдена!"
        )

    context = {
        "request": request,
        "modification": modification,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "si_modifications/update_or_create.html",
        context=context
    )
