from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)
from core.db.dependencies import get_company_timezone
from core.config import settings
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import NotFoundError

from infrastructure.db import async_db_session, async_db_session_begin

from apps.company_app.repositories import CalendarReportRepository
from apps.company_app.schemas.calendar_reports import (
    CalendarReportsPage, CalendarReportForm,
    CalendarReportDetail, CalendarReportListItem
)


calendar_reports_api_router = APIRouter(
    prefix="/api/calendar-reports"
)


@calendar_reports_api_router.get(
    "/",
    response_model=CalendarReportsPage
)
async def api_get_calendar_reports(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1, le=settings.max_int),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    calendar_report_repo = CalendarReportRepository(session)
    objs, page, total_pages = await calendar_report_repo.get_paginated(
        company_id, page, settings.entries_per_page, search
    )

    items = []
    for obj in objs:
        item_dict = CalendarReportListItem.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(CalendarReportListItem(**item_dict))

    return {"items": items, "page": page, "total_pages": total_pages}


@calendar_reports_api_router.get(
    "/report",
    response_model=CalendarReportDetail
)
async def api_get_calendar_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    calendar_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    calendar_report_repo = CalendarReportRepository(session)
    report = await calendar_report_repo.get_by_id(
        calendar_report_id, company_id
    )

    if not report:
        raise NotFoundError(
            detail="Календарный отчёт не найден!"
        )

    item_dict = CalendarReportDetail.model_validate(report).model_dump()
    item_dict["created_at_strftime_full"] = format_datetime_tz(
        report.created_at, company_tz, "%d.%m.%Y %H:%M"
    )
    item_dict["updated_at_strftime_full"] = format_datetime_tz(
        report.updated_at, company_tz, "%d.%m.%Y %H:%M"
    )

    return CalendarReportDetail(**item_dict)


@calendar_reports_api_router.post("/create")
async def api_create_calendar_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    calendar_report_data: CalendarReportForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    calendar_report_repo = CalendarReportRepository(session)

    fields_state = calendar_report_data.fields_state
    fields_order_str = ",".join(calendar_report_data.fields_order)

    db_data = {
        "name": calendar_report_data.name,
        "fields_order": fields_order_str,
        "for_auditor": calendar_report_data.for_auditor,
        "for_dispatcher1": calendar_report_data.for_dispatcher1,
        "for_dispatcher2": calendar_report_data.for_dispatcher2,
        "no_date": calendar_report_data.no_date,
        # Поля из fields_state
        "dispatcher": fields_state.get("dispatcher", False),
        "route": fields_state.get("route", False),
        "date": fields_state.get("date", False),
        "address": fields_state.get("address", False),
        "phone_number": fields_state.get("phone_number", False),
        "sec_phone_number": fields_state.get("sec_phone_number", False),
        "client_full_name": fields_state.get("client_full_name", False),
        "legal_entity": fields_state.get("legal_entity", False),
        "counter_number": fields_state.get("counter_number", False),
        "water_type": fields_state.get("water_type", False),
        "price": fields_state.get("price", False),
        "status": fields_state.get("status", False),
        "additional_info": fields_state.get("additional_info", False),
        "deleted_at": fields_state.get("deleted_at", False),
    }

    await calendar_report_repo.create(company_id, **db_data)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@calendar_reports_api_router.put("/update")
async def api_update_calendar_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    calendar_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    calendar_report_data: CalendarReportForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    calendar_report_repo = CalendarReportRepository(session)
    report = await calendar_report_repo.get_by_id(
        calendar_report_id, company_id
    )

    if not report:
        raise NotFoundError(
            detail="Календарный отчёт не найден!"
        )

    fields_state = calendar_report_data.fields_state
    fields_order_str = ",".join(calendar_report_data.fields_order)

    db_data = {
        "name": calendar_report_data.name,
        "fields_order": fields_order_str,
        "for_auditor": calendar_report_data.for_auditor,
        "for_dispatcher1": calendar_report_data.for_dispatcher1,
        "for_dispatcher2": calendar_report_data.for_dispatcher2,
        "no_date": calendar_report_data.no_date,
        # Поля из fields_state
        "dispatcher": fields_state.get("dispatcher", False),
        "route": fields_state.get("route", False),
        "date": fields_state.get("date", False),
        "address": fields_state.get("address", False),
        "phone_number": fields_state.get("phone_number", False),
        "sec_phone_number": fields_state.get("sec_phone_number", False),
        "client_full_name": fields_state.get("client_full_name", False),
        "legal_entity": fields_state.get("legal_entity", False),
        "counter_number": fields_state.get("counter_number", False),
        "water_type": fields_state.get("water_type", False),
        "price": fields_state.get("price", False),
        "status": fields_state.get("status", False),
        "additional_info": fields_state.get("additional_info", False),
        "deleted_at": fields_state.get("deleted_at", False),
    }

    await calendar_report_repo.update(report, **db_data)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@calendar_reports_api_router.delete("/delete")
async def api_delete_calendar_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    calendar_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    calendar_report_repo = CalendarReportRepository(session)
    report = await calendar_report_repo.get_by_id(
        calendar_report_id, company_id
    )

    if not report:
        raise NotFoundError(
            detail="Календарный отчёт не найден!"
        )

    await calendar_report_repo.delete(report)
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
