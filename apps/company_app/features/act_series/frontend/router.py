from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.common import make_context
from apps.company_app.repositories import ActSeriesRepository


act_series_frontend_router = APIRouter(
    prefix="/act-series"
)


@act_series_frontend_router.get("/")
async def view_act_series(
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
        "act_series/view.html", context=context
    )


@act_series_frontend_router.get("/create")
async def create_act_series(
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
        "act_series/update_or_create.html", context=context
    )


@act_series_frontend_router.get("/update")
async def update_act_series(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    act_series_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    act_series_repo = ActSeriesRepository(session)
    act_series = await act_series_repo.get_by_id(act_series_id, company_id)

    if not act_series:
        raise NotFoundError(
            company_id=company_id,
            detail="Серия бланка не найдена!"
        )

    context = {
        "request": request,
        "view_type": "update",
        "act_series": act_series,
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "act_series/update_or_create.html", context=context
    )
