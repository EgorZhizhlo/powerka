from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData, check_include_in_active_company
)

from infrastructure.db import async_db_session_begin

from core.config import settings
from core.exceptions.api.common import (
    NotFoundError, BadRequestError
)

from apps.company_app.repositories import CompanyActivityRepository
from apps.company_app.schemas.equipments import (
    ItemCreate, ItemUpdate, ItemOut, OkResponse
)


activities_router = APIRouter(prefix="/api/equipments/activities")


@activities_router.get(
    "/",
    response_model=List[ItemOut],
)
async def get_activities(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanyActivityRepository(session)
    return await repo.get_activities_in_company(company_id)


@activities_router.post(
    "/activity",
    response_model=ItemOut
)
async def create_activity(
    data: ItemCreate,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanyActivityRepository(session)

    if await repo.exists_activity_by_name_in_company(data.name, company_id):
        raise BadRequestError(
            detail="Такой вид измерений уже существует!"
        )

    return await repo.create_activity(name=data.name, company_id=company_id)


@activities_router.put(
    "/activity",
    response_model=ItemOut
)
async def update_activity(
    data: ItemUpdate,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    activity_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanyActivityRepository(session)

    activity = await repo.get_activity_by_id_in_company(
        activity_id, company_id)
    if not activity:
        raise NotFoundError(
            company_id=company_id,
            detail="Вид измерений не найден!"
        )

    if data.name.strip().lower() != activity.name.strip().lower():
        if await repo.exists_activity_by_name_in_company(
                data.name, company_id):
            raise BadRequestError(
                detail="Такой вид измерений уже существует!"
            )

    return await repo.update_activity(activity, new_name=data.name)


@activities_router.delete(
    "/activity",
    response_model=OkResponse)
async def delete_activity_item(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    activity_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanyActivityRepository(session)

    activity = await repo.get_activity_by_id_in_company(
        activity_id, company_id
    )
    if not activity:
        raise NotFoundError(
            company_id=company_id,
            detail="Вид измерений не найден!"
        )

    await repo.delete_activity(activity)
    return OkResponse(ok=True)
