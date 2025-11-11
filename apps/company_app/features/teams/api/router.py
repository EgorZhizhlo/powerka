import math
from fastapi import (
    APIRouter, Response, HTTPException, status as status_code,
    Depends, Query, Body)

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from models import VerifierModel, TeamModel

from apps.company_app.schemas.teams import (
    TeamCreate, TeamsPage, TeamOut, VerifierShort
)


teams_api_router = APIRouter(
    prefix="/api/teams"
)


@teams_api_router.get("/", response_model=TeamsPage)
async def api_get_teams(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    status: str = Query("all", pattern="^(all|active|deleted)$"),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    filters = [TeamModel.company_id == company_id]
    if search:
        filters.append(TeamModel.name.ilike(f"%{search}%"))
    if status == "active":
        filters.append(TeamModel.is_deleted.isnot(True))
    elif status == "deleted":
        filters.append(TeamModel.is_deleted.is_(True))

    total = (await session.execute(
        select(func.count(TeamModel.id)).where(*filters)
    )).scalar_one()

    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    q = (
        select(TeamModel)
        .where(*filters)
        .options(
            selectinload(TeamModel.verifiers)
        )
        .order_by(
            TeamModel.is_deleted.isnot(True).desc(),
            TeamModel.id.desc()
        )
        .limit(per_page).offset(offset)
    )
    rows = (await session.execute(q)).scalars().all()

    items: list[TeamOut] = []
    for obj in rows:
        out = TeamOut(
            id=obj.id,
            name=obj.name,
            is_deleted=bool(obj.is_deleted),
            created_at_strftime_full=format_datetime_tz(
                obj.created_at, company_tz, "%d.%m.%Y %H:%M"
            ),
            updated_at_strftime_full=format_datetime_tz(
                obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
            ),
            verifiers=[
                VerifierShort.model_validate(v, from_attributes=True)
                for v in (obj.verifiers or [])
            ],
        )
        items.append(out)

    return TeamsPage(items=items, page=page, total_pages=total_pages)


@teams_api_router.post("/create")
async def api_create_team(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    team_data: TeamCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_team = TeamModel(
        name=team_data.name,
        company_id=company_id
    )

    if team_data.verifiers:
        verifiers_objects = await session.execute(
            select(VerifierModel)
            .where(VerifierModel.id.in_(team_data.verifiers))
        )
        new_team.verifiers.extend(verifiers_objects.scalars().all())

    session.add(new_team)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@teams_api_router.put("/update")
async def api_update_team(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    team_id: int = Query(..., ge=1, le=settings.max_int),
    team_data: TeamCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    team = (await session.execute(
        select(TeamModel)
        .where(
            TeamModel.company_id == company_id,
            TeamModel.id == team_id)
        .options(selectinload(TeamModel.verifiers))
    )).scalar_one_or_none()

    await check_is_none(
        team, type="Команда", id=team_id, company_id=company_id)

    updated_fields = team_data.model_dump(exclude_unset=True)
    for key, value in updated_fields.items():
        if key == "verifiers":
            related_objs = await session.execute(
                select(VerifierModel)
                .where(VerifierModel.id.in_(value if value else []))
            )
            setattr(team, key, related_objs.scalars().all())
        else:
            setattr(team, key, value)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@teams_api_router.delete("/delete", status_code=204)
async def api_delete_team(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    team_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    team = (
        await session.execute(
            select(TeamModel)
            .where(TeamModel.company_id == company_id, TeamModel.id == team_id)
            .options(
                selectinload(TeamModel.verifiers)
                .selectinload(VerifierModel.verification)
            )
        )
    ).scalar_one_or_none()

    if team is None:
        raise HTTPException(404, "Команда не найдена")

    has_any_verification = any(
        bool(v.verification) for v in (team.verifiers or [])
    )

    if has_any_verification:
        team.is_deleted = True
        for v in team.verifiers or []:
            v.team = None
        team.verifiers.clear()
    else:
        for v in team.verifiers or []:
            v.team = None
        team.verifiers.clear()
        await session.delete(team)

    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@teams_api_router.post("/restore", status_code=200)
async def api_restore_team(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    team_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    team = (
        await session.execute(
            select(TeamModel)
            .where(TeamModel.company_id == company_id,
                   TeamModel.id == team_id,
                   TeamModel.is_deleted.is_(True))
        )
    ).scalar_one_or_none()

    if team is None:
        raise HTTPException(404, "Удалённая команда не найдена")

    team.is_deleted = False
    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
