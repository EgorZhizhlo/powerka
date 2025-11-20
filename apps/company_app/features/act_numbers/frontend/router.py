from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
)

from infrastructure.db import async_db_session

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from apps.company_app.common import make_context
from apps.company_app.repositories import (
    CityRepository, ActSeriesRepository, ActNumberRepository
)

act_numbers_frontend_router = APIRouter(
    prefix="/act-numbers"
)


@act_numbers_frontend_router.get("/")
async def view_act_numbers(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
        "per_page": settings.entries_per_page,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "act_numbers/view.html",
        context=context
    )


@act_numbers_frontend_router.get("/create")
async def view_create_act_number(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    city_repo = CityRepository(session)
    cities = await city_repo.get_all_by_company(company_id)

    act_series_repo = ActSeriesRepository(session)
    act_series = await act_series_repo.get_all_by_company(company_id)

    context = {
        "request": request,
        "cities": cities,
        "act_series": act_series,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "act_numbers/update_or_create.html",
        context=context
    )


@act_numbers_frontend_router.get("/update")
async def view_update_act_number(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_number_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    city_repo = CityRepository(session)
    cities = await city_repo.get_all_by_company(company_id)

    act_series_repo = ActSeriesRepository(session)
    act_series = await act_series_repo.get_all_by_company(company_id)

    act_number_repo = ActNumberRepository(session)
    act_number_entry = await act_number_repo.get_by_id(
        act_number_id, company_id
    )

    if not act_number_entry:
        raise NotFoundError(
            company_id=company_id,
            detail="Номер акта не найден!"
        )

    context = {
        "request": request,
        "view_type": "update",
        "act_number_entry": act_number_entry,
        "act_series": act_series,
        "cities": cities,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "act_numbers/update_or_create.html",
        context=context
    )
