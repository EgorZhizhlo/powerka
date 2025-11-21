from typing import Optional
from fastapi import APIRouter, Depends, Query

from core.config import settings

from access_control import JwtData, check_access_verification

from apps.verification_app.schemas.registry_number import (
    RegistryNumberResponse
)
from apps.verification_app.repositories import (
    RegistryNumberRepository, read_registry_number_repository
)


registry_number_router = APIRouter(prefix="/api/registry-numbers")


@registry_number_router.get(
    "/",
    response_model=Optional[RegistryNumberResponse]
)
async def get_registry_number(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    registry_number_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_access_verification),
    repo: RegistryNumberRepository = Depends(
        read_registry_number_repository
    )
):
    return await repo.find_by_id(
        registry_number_id=registry_number_id)
