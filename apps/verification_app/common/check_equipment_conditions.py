from core.templates.jinja_filters import get_current_date_in_tz
from core.cache.company_timezone_cache import company_tz_cache
from apps.verification_app.exceptions import (
    VerificationEquipmentException, VerificationEquipmentExpiredException,
    CustomVerificationEquipmentException,
    CustomVerificationEquipmentExpiredException
)
from models.enums import EquipmentInfoType


async def check_equip_conditions(
        equipments, company_id: int = None, for_view: bool = False
) -> None:
    if not equipments:
        if for_view:
            raise CustomVerificationEquipmentException
        raise VerificationEquipmentException

    company_tz = "Europe/Moscow"
    if company_id:
        company_tz = await company_tz_cache.get_timezone(company_id)
    
    today = get_current_date_in_tz(company_tz)
    expired_equipment = []

    for equipment in equipments:
        if not equipment.equipment_info:
            continue

        verif_infos = [
            info
            for info in equipment.equipment_info
            if info.type == EquipmentInfoType.verification
        ]

        if not verif_infos:
            continue

        latest_info = max(
            verif_infos,
            key=lambda x: x.date_to
        )

        if (
            latest_info.date_to is None
            or latest_info.date_to < today
        ):
            expired_equipment.append(
                f"{equipment.name} (Зав. № {equipment.factory_number})"
            )

    if expired_equipment:
        if for_view:
            raise CustomVerificationEquipmentExpiredException(
                equipments=expired_equipment
            )
        raise VerificationEquipmentExpiredException(
            equipments=expired_equipment
        )
