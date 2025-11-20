import math
from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.templates.jinja_filters import format_datetime_tz
from core.exceptions.api.common import NotFoundError

from infrastructure.db import async_db_session, async_db_session_begin
from models import VerificationReportModel

from access_control import (
    JwtData, check_include_in_not_active_company,
    check_include_in_active_company
)

from apps.company_app.schemas.verification_reports import (
    VerificationReportsPage, VerificationReportForm,
    VerificationReportListItem, VerificationReportDetail
)


verification_reports_api_router = APIRouter(
    prefix="/api/verification-reports"
)


@verification_reports_api_router.get(
    "/",
    response_model=VerificationReportsPage
)
async def api_get_verification_reports(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    search: str = Query(""),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    per_page = settings.entries_per_page

    filters = [VerificationReportModel.company_id == company_id]
    if search:
        filters.append(VerificationReportModel.name.ilike(f"%{search}%"))

    total = (await session.execute(
        select(func.count(VerificationReportModel.id)).where(*filters)
    )).scalar_one()

    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    q = (select(VerificationReportModel)
         .where(*filters)
         .order_by(VerificationReportModel.id.desc())
         .limit(per_page).offset(offset))

    rows = (await session.execute(q)).scalars().all()

    items: list[VerificationReportListItem] = []
    for obj in rows:
        item_dict = VerificationReportListItem.model_validate(obj).model_dump()
        item_dict["created_at_strftime_full"] = format_datetime_tz(
            obj.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item_dict["updated_at_strftime_full"] = format_datetime_tz(
            obj.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(VerificationReportListItem(**item_dict))

    return VerificationReportsPage(
        items=items,
        page=page,
        total_pages=total_pages
    )


@verification_reports_api_router.get(
    "/report",
    response_model=VerificationReportDetail
)
async def api_get_verification_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
):
    report = (
        await session.execute(
            select(VerificationReportModel)
            .where(
                VerificationReportModel.company_id == company_id,
                VerificationReportModel.id == verification_report_id
            )
        )
    ).scalar_one_or_none()

    if not report:
        raise NotFoundError(
            company_id=company_id,
            detail="Настраиваемый отчет поверки не найден!"
        )

    report_dict = VerificationReportDetail.model_validate(report).model_dump()
    report_dict["created_at_strftime_full"] = format_datetime_tz(
        report.created_at, company_tz, "%d.%m.%Y %H:%M"
    )
    report_dict["updated_at_strftime_full"] = format_datetime_tz(
        report.updated_at, company_tz, "%d.%m.%Y %H:%M"
    )

    return VerificationReportDetail(**report_dict)


@verification_reports_api_router.post("/create")
async def api_create_verification_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    report_data: VerificationReportForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    fields_state = report_data.fields_state
    fields_order_str = ",".join(report_data.fields_order)

    report = VerificationReportModel(
        company_id=company_id,
        name=report_data.name,
        fields_order=fields_order_str,
        for_verifier=report_data.for_verifier,
        for_auditor=report_data.for_auditor,
        # Основные поля
        employee_name=fields_state.get("employee_name", False),
        verification_date=fields_state.get("verification_date", False),
        city=fields_state.get("city", False),
        address=fields_state.get("address", False),
        client_name=fields_state.get("client_name", False),
        si_type=fields_state.get("si_type", False),
        registry_number=fields_state.get("registry_number", False),
        factory_number=fields_state.get("factory_number", False),
        location_name=fields_state.get("location_name", False),
        meter_info=fields_state.get("meter_info", False),
        end_verification_date=fields_state.get("end_verification_date", False),
        series_name=fields_state.get("series_name", False),
        act_number=fields_state.get("act_number", False),
        verification_result=fields_state.get("verification_result", False),
        verification_number=fields_state.get("verification_number", False),
        qh=fields_state.get("qh", False),
        modification_name=fields_state.get("modification_name", False),
        water_type=fields_state.get("water_type", False),
        method_name=fields_state.get("method_name", False),
        reference=fields_state.get("reference", False),
        seal=fields_state.get("seal", False),
        phone_number=fields_state.get("phone_number", False),
        verifier_name=fields_state.get("verifier_name", False),
        manufacture_year=fields_state.get("manufacture_year", False),
        reason_name=fields_state.get("reason_name", False),
        interval=fields_state.get("interval", False),
        # Дополнительные поля
        additional_checkbox_1=fields_state.get("additional_checkbox_1", False),
        additional_checkbox_2=fields_state.get("additional_checkbox_2", False),
        additional_checkbox_3=fields_state.get("additional_checkbox_3", False),
        additional_checkbox_4=fields_state.get("additional_checkbox_4", False),
        additional_checkbox_5=fields_state.get("additional_checkbox_5", False),
        additional_input_1=fields_state.get("additional_input_1", False),
        additional_input_2=fields_state.get("additional_input_2", False),
        additional_input_3=fields_state.get("additional_input_3", False),
        additional_input_4=fields_state.get("additional_input_4", False),
        additional_input_5=fields_state.get("additional_input_5", False),
    )

    session.add(report)
    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@verification_reports_api_router.put("/update")
async def api_update_verification_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    report_data: VerificationReportForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    report = (
        await session.execute(
            select(VerificationReportModel)
            .where(
                VerificationReportModel.company_id == company_id,
                VerificationReportModel.id == verification_report_id
            )
        )
    ).scalar_one_or_none()

    if not report:
        raise NotFoundError(
            company_id=company_id,
            detail="Настраиваемый отчет поверки не найден!"
        )

    fields_state = report_data.fields_state
    fields_order_str = ",".join(report_data.fields_order)

    # Обновляем базовые поля
    report.name = report_data.name
    report.fields_order = fields_order_str
    report.for_verifier = report_data.for_verifier
    report.for_auditor = report_data.for_auditor

    # Обновляем основные поля
    report.employee_name = fields_state.get("employee_name", False)
    report.verification_date = fields_state.get("verification_date", False)
    report.city = fields_state.get("city", False)
    report.address = fields_state.get("address", False)
    report.client_name = fields_state.get("client_name", False)
    report.si_type = fields_state.get("si_type", False)
    report.registry_number = fields_state.get("registry_number", False)
    report.factory_number = fields_state.get("factory_number", False)
    report.location_name = fields_state.get("location_name", False)
    report.meter_info = fields_state.get("meter_info", False)
    report.end_verification_date = fields_state.get(
        "end_verification_date", False)
    report.series_name = fields_state.get("series_name", False)
    report.act_number = fields_state.get("act_number", False)
    report.verification_result = fields_state.get("verification_result", False)
    report.verification_number = fields_state.get("verification_number", False)
    report.qh = fields_state.get("qh", False)
    report.modification_name = fields_state.get("modification_name", False)
    report.water_type = fields_state.get("water_type", False)
    report.method_name = fields_state.get("method_name", False)
    report.reference = fields_state.get("reference", False)
    report.seal = fields_state.get("seal", False)
    report.phone_number = fields_state.get("phone_number", False)
    report.verifier_name = fields_state.get("verifier_name", False)
    report.manufacture_year = fields_state.get("manufacture_year", False)
    report.reason_name = fields_state.get("reason_name", False)
    report.interval = fields_state.get("interval", False)

    # Дополнительные поля
    report.additional_checkbox_1 = fields_state.get(
        "additional_checkbox_1", False)
    report.additional_checkbox_2 = fields_state.get(
        "additional_checkbox_2", False)
    report.additional_checkbox_3 = fields_state.get(
        "additional_checkbox_3", False)
    report.additional_checkbox_4 = fields_state.get(
        "additional_checkbox_4", False)
    report.additional_checkbox_5 = fields_state.get(
        "additional_checkbox_5", False)
    report.additional_input_1 = fields_state.get("additional_input_1", False)
    report.additional_input_2 = fields_state.get("additional_input_2", False)
    report.additional_input_3 = fields_state.get("additional_input_3", False)
    report.additional_input_4 = fields_state.get("additional_input_4", False)
    report.additional_input_5 = fields_state.get("additional_input_5", False)

    await session.flush()

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@verification_reports_api_router.delete("/delete")
async def api_delete_verification_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_report_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    report = (await session.execute(
        select(VerificationReportModel).where(
            VerificationReportModel.company_id == company_id,
            VerificationReportModel.id == verification_report_id
        )
    )).scalar_one_or_none()

    if not report:
        raise NotFoundError(
            company_id=company_id,
            detail="Настраиваемый отчет поверки не найден!"
        )

    await session.delete(report)
    await session.flush()
    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
