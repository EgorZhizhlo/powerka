from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import NotFoundError

from infrastructure.db import async_db_session
from models import VerifierModel, TeamModel

from access_control import (
    JwtData, check_include_in_not_active_company,
    check_include_in_active_company)

from apps.company_app.common import make_context


teams_frontend_router = APIRouter(
    prefix="/teams"
)


@teams_frontend_router.get("/")
async def view_teams(
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
        "teams/view.html",
        context=context
    )


@teams_frontend_router.get("/create")
async def view_create_team(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    verifiers = (
        await session.execute(
            select(VerifierModel)
            .where(
                VerifierModel.company_id == company_id
            ).order_by(
                VerifierModel.last_name,
                VerifierModel.name,
                VerifierModel.patronymic
            )
        )
    ).scalars().all()

    context = {
        "request": request,
        "verifiers": verifiers,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "teams/update_or_create.html",
        context=context
    )


@teams_frontend_router.get("/update")
async def view_update_team(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    team_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    team = (await session.execute(
        select(TeamModel)
        .where(
            TeamModel.company_id == company_id,
            TeamModel.id == team_id)
        .options(selectinload(TeamModel.verifiers))
    )).scalar_one_or_none()

    if not team:
        raise NotFoundError(
            company_id=company_id,
            detail="Команда не найдена!"
        )

    verifiers = (
        await session.execute(
            select(VerifierModel)
            .where(VerifierModel.company_id == company_id)
            .order_by(
                VerifierModel.last_name,
                VerifierModel.name,
                VerifierModel.patronymic
            )
        )
    ).scalars().all()

    context = {
        "request": request,
        "verifiers": verifiers,
        "team": team,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "teams/update_or_create.html",
        context=context
    )
