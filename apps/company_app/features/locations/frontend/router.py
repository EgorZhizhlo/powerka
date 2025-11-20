from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session
from models import LocationModel

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.common import make_context


locations_frontend_router = APIRouter(
    prefix="/locations"
)


@locations_frontend_router.get("/")
async def view_locations(
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
        "locations/view.html",
        context=context
    )


@locations_frontend_router.get("/create")
async def view_create_location(
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
        "locations/update_or_create.html",
        context=context
    )


@locations_frontend_router.get("/update")
async def view_edit_location(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    location_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    location = (
        await session.execute(
            select(LocationModel)
            .where(
                LocationModel.company_id == company_id,
                LocationModel.id == location_id
            )
        )
    ).scalar_one_or_none()

    if not location:
        raise NotFoundError(
            company_id=company_id,
            detail="Расположение счетчика не найдено!"
        )

    context = {
        "request": request,
        "view_type": "update",
        "location": location,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "locations/update_or_create.html",
        context=context
    )
