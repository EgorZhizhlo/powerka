from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse

from models import EquipmentModel, CompanyActivityModel

from access_control import (
    JwtData,
    check_include_in_not_active_company
)

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from apps.company_app.common import create_table_report

from infrastructure.db import async_db_session_begin

from urllib.parse import quote

from core.templates.jinja_filters import get_current_date_in_tz
from core.cache.company_timezone_cache import company_tz_cache
from core.config import settings
from core.exceptions.frontend.common import InternalServerError


form2_api_router = APIRouter(
    prefix="/api/equipments/form2"
)


def format_date(value) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")


def format_range(value: str | None) -> str:
    if not value:
        return ""
    parts = [p.strip() for p in value.split("|") if p.strip()]
    return "\n".join(parts)


def format_accuracy(value: str | None) -> str:
    if not value:
        return ""
    parts = [p.strip() for p in value.split("|") if p.strip()]
    return "\n".join(f"ПП±({p})%" for p in parts)


def build_equipment_row(eq: EquipmentModel) -> dict:
    verification_infos = [i for i in eq.equipment_info if i.type == "verification"]
    last_info = (
        max(verification_infos, key=lambda i: i.date_to)
        if verification_infos else None
    )

    si_name = eq.si_type.name if eq.si_type else ""
    activity_name = eq.activity.name if eq.activity else ""
    measurement_type = ", ".join(filter(None, [si_name, activity_name]))

    return {
        "measurement_type": measurement_type,
        "standards": eq.full_name or eq.name,
        "manufacturer": (
            f"{eq.manufacturer_country}, {eq.manufacturer_name} {eq.year_of_issue} г."
            if eq.manufacturer_country and eq.manufacturer_name and eq.year_of_issue else ""
        ),
        "commission_year": (
            f"{eq.commissioning_year} г., Зав.№ {eq.factory_number}, Инв.№ {eq.inventory_number}"
            if eq.commissioning_year else ""
        ),
        "range": format_range(eq.measurement_range),
        "accuracy": format_accuracy(eq.error_or_uncertainty),
        "certificate": (
            f"Свидетельство о поверке {last_info.info} от {format_date(last_info.date_from)}"
            if last_info and last_info.date_from else ""
        ),
        "ownership": eq.ownership_document or "",
        "location": eq.storage_place or "",
        "note": (
            f"https://fgis.gost.ru/fundmetrology/cm/results/1-{last_info.info.split('/')[-1]}"
            if last_info and last_info.info and "/" in last_info.info else ""
        ),
    }


@form2_api_router.get("/export")
async def get_autodocument_form2_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_not_active_company),
):
    company_tz = await company_tz_cache.get_timezone(company_id)

    try:
        result = await session.execute(
            select(CompanyActivityModel)
            .options(
                selectinload(CompanyActivityModel.equipments)
                .options(
                    selectinload(EquipmentModel.si_type),
                    selectinload(EquipmentModel.activity),
                    selectinload(EquipmentModel.equipment_info),
                )
            )
            .where(CompanyActivityModel.company_id == company_id)
        )
        activities: list[CompanyActivityModel] = result.scalars().all()

        sections: list[dict] = []
        for activity in activities:
            rows = [
                build_equipment_row(eq)
                for eq in activity.equipments
                if not eq.is_deleted
            ]
            if rows:
                sections.append({
                    "section_title": activity.name,
                    "rows": rows
                })

        buf = create_table_report(sections)

        current_date = get_current_date_in_tz(company_tz)
        filename = f"Форма 2 от {format_date(current_date)}.xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"
            },
        )

    except Exception as e:
        raise InternalServerError(
            detail=f"Не удалось сформировать отчёт: {e}",
            company_id=company_id
        )
