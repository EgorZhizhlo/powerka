from fastapi import APIRouter, Response, Depends, Query, Body

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session_begin
from models import MetrologInfoModel
from models.enums import ReasonType

from access_control import (
    JwtData,
    check_active_access_verification
)

from core.config import settings
from apps.verification_app.exceptions import (
    VerificationVerifierException,

    CreateMetrologInfoAccessException,
    UpdateMetrologInfoAccessException,
    DeleteMetrologInfoAccessException
)
from apps.verification_app.common import (
    check_equip_conditions, clear_verification_cache
)
from apps.verification_app.repositories import (
    MetrologInfoRepository, action_metrolog_info_repository,
    ReasonRepository, read_reason_repository,
)

from apps.verification_app.schemas.metrologs_control_a import MetrologInfoForm


metrologs_control_api_router = APIRouter(prefix='/api/metrologs-control')
VER_PHOTO_LIMIT = settings.VERIFICATION_PHOTO_LIMIT


@metrologs_control_api_router.post("/create")
async def create_metrolog_info(
    metrolog_info_data: MetrologInfoForm = Body(...),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    metrolog_info_repo: MetrologInfoRepository = Depends(
        action_metrolog_info_repository
    ),
    reason_repo: ReasonRepository = Depends(
        read_reason_repository
    ),
):
    status = employee_data.status
    employee_id = employee_data.id

    check_exist_metrolog = await metrolog_info_repo.check_exist_metrolog_info(
        verification_entry_id=verification_entry_id
    )
    if check_exist_metrolog:
        raise CreateMetrologInfoAccessException

    verification_entry = await metrolog_info_repo.get_for_create(
        verification_entry_id=verification_entry_id,
        employee_id=employee_id, status=status
    )

    if not verification_entry:
        raise CreateMetrologInfoAccessException

    if not verification_entry.verifier_id:
        raise VerificationVerifierException

    check_equip_conditions(verification_entry.equipments)

    if metrolog_info_data.high_error_rate:
        reason_id = await reason_repo.get_reason_id_by_type(
            reason_type=ReasonType.p_2_7_3,
        )
        verification_entry.reason_id = reason_id
        verification_entry.verification_result = False

    metrolog_entry = MetrologInfoModel(
        company_id=company_id,
        verification_id=verification_entry_id
    )

    for key, value in metrolog_info_data.model_dump().items():
        setattr(metrolog_entry, key, value)

    session.add(metrolog_entry)
    await session.flush()

    await clear_verification_cache(company_id)

    return Response(status_code=204)


@metrologs_control_api_router.post("/update")
async def update_metrolog_info(
    metrolog_info_data: MetrologInfoForm = Body(...),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    metrolog_info_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    metrolog_info_repo: MetrologInfoRepository = Depends(
        action_metrolog_info_repository
    ),
    reason_repo: ReasonRepository = Depends(
        read_reason_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    metrolog_info = await metrolog_info_repo.get_for_update(
        metrolog_info_id=metrolog_info_id,
        verification_entry_id=verification_entry_id,
        employee_id=employee_id, status=status
    )
    if not metrolog_info:
        raise UpdateMetrologInfoAccessException

    if not metrolog_info.verification.verifier_id:
        raise VerificationVerifierException

    check_equip_conditions(metrolog_info.verification.equipments)

    if metrolog_info_data.high_error_rate:
        reason_id = await reason_repo.get_reason_id_by_type(
            reason_type=ReasonType.p_2_7_3,
        )
        metrolog_info.verification.reason_id = reason_id
        metrolog_info.verification.verification_result = False

    for key, value in metrolog_info_data.model_dump().items():
        setattr(metrolog_info, key, value)

    await session.flush()

    await clear_verification_cache(company_id)

    return Response(status_code=204)


@metrologs_control_api_router.delete("/delete")
async def delete_metrolog_info(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    metrolog_info_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_active_access_verification),
    metrolog_info_repo: MetrologInfoRepository = Depends(
        action_metrolog_info_repository
    )
):
    status = user_data.status
    employee_id = user_data.id

    deleted = await metrolog_info_repo.try_delete_entry(
        metrolog_info_id, verification_entry_id, employee_id, status
    )
    if not deleted:
        raise DeleteMetrologInfoAccessException

    await clear_verification_cache(company_id)
    return Response(status_code=204)
