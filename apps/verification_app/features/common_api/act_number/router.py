from typing import Optional
from fastapi import APIRouter, Query, Depends

from core.config import settings

from access_control import JwtData, check_access_verification

from apps.verification_app.schemas.act_number import ActNumberResponse
from apps.verification_app.repositories import (
    ActNumberRepository, read_act_number_repository
)


act_number_router = APIRouter(prefix='/api/act-numbers')


@act_number_router.get(
    "/by-number/",
    response_model=Optional[ActNumberResponse])
async def get_act_number_by_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    series_id: int = Query(..., ge=1, le=settings.max_int),
    act_number: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_access_verification
    ),
    repo: ActNumberRepository = Depends(
        read_act_number_repository
    )
):
    act_num = await repo.find_by_number(
        series_id=series_id, act_number=act_number
    )

    return act_num
