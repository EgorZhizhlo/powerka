from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData, check_include_in_active_company
)
from core.config import settings
from core.exceptions.api.common import (
    NotFoundError, BadRequestError
)

from infrastructure.db import async_db_session_begin

from apps.company_app.repositories import CompanySiTypeRepository
from apps.company_app.schemas.equipments import (
    ItemCreate, ItemUpdate, ItemOut, OkResponse
)


si_types_router = APIRouter(prefix="/api/equipments/si-types")


@si_types_router.get(
    "/",
    response_model=List[ItemOut]
)
async def get_si_types(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanySiTypeRepository(session)
    return await repo.get_si_types_in_company(company_id)


@si_types_router.post(
    "/si-type",
    response_model=ItemOut
)
async def create_si_type(
    data: ItemCreate,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanySiTypeRepository(session)

    if await repo.exists_si_type_by_name_in_company(data.name, company_id):
        raise BadRequestError(
            detail="Такой тип СИ уже существует!",
        )

    return await repo.create_si_type(name=data.name, company_id=company_id)


@si_types_router.put(
    "/si-type",
    response_model=ItemOut
)
async def update_si_type(
    data: ItemUpdate,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    si_type_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanySiTypeRepository(session)

    si_type = await repo.get_si_type_by_id_in_company(si_type_id, company_id)
    if not si_type:
        raise NotFoundError(
            company_id=company_id,
            detail="Тип СИ не найден!"
        )

    if data.name.strip().lower() != si_type.name.strip().lower():
        if await repo.exists_si_type_by_name_in_company(data.name, company_id):
            raise BadRequestError(
                detail="Такой тип СИ уже существует!",
            )

    return await repo.update_si_type(si_type, new_name=data.name)


@si_types_router.delete(
    "/si-type",
    response_model=OkResponse
)
async def delete_si_type(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    si_type_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    repo = CompanySiTypeRepository(session)

    si_type = await repo.get_si_type_by_id_in_company(si_type_id, company_id)
    if not si_type:
        raise NotFoundError(
            company_id=company_id,
            detail="Тип СИ не найден!"
        )

    await repo.delete_si_type(si_type)
    return OkResponse(ok=True)
