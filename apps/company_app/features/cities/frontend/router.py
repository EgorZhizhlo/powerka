from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session

from apps.company_app.repositories import CityRepository
from apps.company_app.common import make_context


cities_frontend_router = APIRouter(
    prefix="/cities"
)


@cities_frontend_router.get("/")
async def view_cities(
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
        "cities/view.html",
        context=context
    )


@cities_frontend_router.get("/create")
async def view_create_city(
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
        "cities/update_or_create.html",
        context=context
    )


@cities_frontend_router.get("/update")
async def view_update_city(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    city_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    city_repo = CityRepository(session)
    city = await city_repo.get_by_id(city_id, company_id)

    if not city:
        raise NotFoundError(
            company_id=company_id,
            detail="Населённый пункт не найден!"
        )

    context = {
        "request": request,
        "city": city,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "cities/update_or_create.html",
        context=context
    )
