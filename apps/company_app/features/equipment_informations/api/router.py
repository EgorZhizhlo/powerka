from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_active_company
)

from core.config import settings
from core.exceptions.api.common import NotFoundError

from infrastructure.db import async_db_session_begin

from models import EquipmentModel, EquipmentInfoModel
from models.enums.equipment_info import EquipmentInfoType

from apps.company_app.schemas.equipment_informations import (
    EquipmentInfoCreate
)


equipment_informations_api_router = APIRouter(
    prefix="/api/equipment-informations"
)


@equipment_informations_api_router.post("/create")
async def api_create_equipment_information(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    type_verif: EquipmentInfoType = Query(...),
    equipment_info_data: EquipmentInfoCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    new_equipment = EquipmentInfoModel(
        type=type_verif,
        date_from=equipment_info_data.date_from,
        date_to=equipment_info_data.date_to,
        info=equipment_info_data.info,
        equipment_id=equipment_id,
    )
    session.add(new_equipment)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@equipment_informations_api_router.put("/update")
async def api_update_equipment_information(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_info_id: int = Query(..., ge=1, le=settings.max_int),
    equipment_info_data: EquipmentInfoCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):

    equipment_info = (
        await session.execute(
            select(EquipmentInfoModel)
            .join(EquipmentInfoModel.equipment)
            .where(EquipmentInfoModel.id == equipment_info_id,
                   EquipmentModel.id == equipment_id,
                   EquipmentModel.company_id == company_id)
        )
    ).scalar_one_or_none()

    if not equipment_info:
        raise NotFoundError(
            company_id=company_id,
            detail="ТО и Поверка оборудования не найдена!"
        )

    for key, value in equipment_info_data.model_dump().items():
        setattr(equipment_info, key, value)

    session.add(equipment_info)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
