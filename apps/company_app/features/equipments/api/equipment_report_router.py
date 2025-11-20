from fastapi import APIRouter, Query, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import io
from fastapi.responses import StreamingResponse

from access_control import (
    JwtData, check_include_in_not_active_company
)

from models import (
    VerifierEquipmentHistoryModel,
    VerifierModel,
    EquipmentModel,
)
from models.enums import VerifierEquipmentAction

from core.config import settings
from core.exceptions.api.common import (
    BadRequestError
)

from infrastructure.db import async_db_session_begin


equipment_report_api_router = APIRouter(
    prefix="/api/equipments/equipment-history")


@equipment_report_api_router.get("/export")
async def export_equipment_history_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    force_signature: bool = Query(False),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if date_from >= date_to:
        raise BadRequestError(
            detail="'Дата до' должна быть больше 'Дата от'!"
        )

    query = (
        select(
            VerifierEquipmentHistoryModel,
            VerifierModel,
            EquipmentModel,
        )
        .join(VerifierEquipmentHistoryModel.verifier)
        .join(VerifierEquipmentHistoryModel.equipment)
        .where(
            VerifierModel.company_id == company_id,
            VerifierEquipmentHistoryModel.created_at >= date_from,
            VerifierEquipmentHistoryModel.created_at <= date_to,
        )
        .order_by(
            VerifierEquipmentHistoryModel.verifier_id,
            VerifierEquipmentHistoryModel.equipment_id,
            VerifierEquipmentHistoryModel.created_at
        )
    )

    result = await session.execute(query)
    rows = result.all()

    history_map = {}
    for history, verifier, equipment in rows:
        key = (verifier.id, equipment.id)
        if key not in history_map:
            history_map[key] = {
                "verifier": verifier,
                "equipment": equipment,
                "accepted": [],
                "declined": []
            }
        if history.action == VerifierEquipmentAction.accepted:
            history_map[key]["accepted"].append(history)
        elif history.action == VerifierEquipmentAction.declined:
            history_map[key]["declined"].append(history)

    # --- Собираем данные для отчета ---
    report_data = []
    idx = 1

    for (verifier_id, equipment_id), data in history_map.items():
        verifier = data["verifier"]
        equipment = data["equipment"]

        accepted_list = sorted(data["accepted"], key=lambda h: h.created_at)
        declined_list = sorted(data["declined"], key=lambda h: h.created_at)

        # Каждое accepted событие может иметь своё declined (ближайшее по времени >=)
        for accepted in accepted_list:
            declined_date = None
            for declined in declined_list:
                if declined.created_at >= accepted.created_at:
                    declined_date = declined.created_at
                    # удаляем найденное, чтобы не использовать повторно
                    declined_list.remove(declined)
                    break

            fio = f"{verifier.last_name} {verifier.name} {
                verifier.patronymic or ''}".strip()
            equipment_name = equipment.full_name or equipment.name
            factory_info = f"{equipment.factory_number or ''} / {
                equipment.inventory_number or ''}"

            report_data.append({
                "№ п/п": idx,
                "ФИО": fio,
                "Наименование оборудования": equipment_name,
                "Заводской №/Инв.№": factory_info,
                "Дата выдачи": accepted.created_at.strftime("%d.%m.%Y"),
                "Дата сдачи": declined_date.strftime(
                    "%d.%m.%Y") if declined_date else "",
                "Подпись": "Подписано ЭЦП" if (
                    declined_date or force_signature) else "",
            })
            idx += 1

    # --- Генерация Excel ---
    df = pd.DataFrame(report_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Отчет")
        sheet = writer.sheets["Отчет"]

        # Автоматическая ширина колонок
        for column_cells in sheet.columns:
            length = max(len(str(cell.value)) if cell.value else 0 for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = length + 2

    output.seek(0)
    filename = f"Журнал_выдачи_оборудования_{date_from.date()}_{date_to.date()}.xlsx"
    encoded_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
    }
    return StreamingResponse(
        output, headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
