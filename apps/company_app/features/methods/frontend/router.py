from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session
from models import MethodModel
from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from apps.company_app.common import make_context


methods_frontend_router = APIRouter(
    prefix="/methods"
)


@methods_frontend_router.get("/")
async def view_methods(
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
        "methods/view.html",
        context=context
    )


@methods_frontend_router.get("/create")
async def view_create_method(
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
        "methods/update_or_create.html",
        context=context
    )


@methods_frontend_router.get("/update")
async def view_update_method(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    method_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    method = (
        await session.execute(
            select(MethodModel)
            .where(
                MethodModel.id == method_id,
                MethodModel.company_id == company_id
            )
        )
    ).scalar_one_or_none()

    if not method:
        raise NotFoundError(
            company_id=company_id,
            detail="Методика не найдена!"
        )

    context = {
        "request": request,
        "method": method,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "methods/update_or_create.html",
        context=context
    )
