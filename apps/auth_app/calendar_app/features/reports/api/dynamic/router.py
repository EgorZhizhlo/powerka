from fastapi import APIRouter, HTTPException, Query, Depends
import pandas as pd
from io import BytesIO
from urllib.parse import quote
from fastapi.responses import StreamingResponse

from core.utils.time_utils import date_utc_now
from core.config import settings
from core.reports.excel_utils import autofit_columns
from core.utils.cpu_bounds_runner import run_cpu_bounds_task

from models.enums import (
    map_order_status_to_label,
    map_order_water_type_to_label,
    map_verification_legal_entity_to_label,
    EmployeeStatus,
)

from access_control import (
    JwtData,
    check_calendar_access,
)

from apps.calendar_app.repositories import (
    CalendarReportRepository,
    read_calendar_report_repository
)

from apps.calendar_app.schemas.dynamic_reports import DynamicReportFilters


reports_dynamic_api_router = APIRouter(
    prefix="/api/reports/dynamic"
)


CALENDAR_COLUMN_NAME_MAP = {
    'dispatcher': 'Диспетчер',
    'route': 'Маршрут',
    'date': 'Дата заявки',
    'address': 'Адрес',
    'phone_number': 'Телефон',
    'sec_phone_number': 'Доп. телефон',
    'client_full_name': 'ФИО клиента',
    'legal_entity': 'Юр. лицо',
    'counter_number': '№ счётчика',
    'water_type': 'Тип воды',
    'price': 'Цена',
    'status': 'Статус',
    'additional_info': 'Доп. информация',
    'date_of_get': 'Дата получения',
}


async def serialize_calendar_entries(entries):
    serialized = []
    for entry in entries:
        row = {
            "date": entry.date,
            "date_of_get": entry.date_of_get,
            "no_date": entry.no_date,
            "address": entry.address,
            "phone_number": entry.phone_number,
            "sec_phone_number": entry.sec_phone_number,
            "client_full_name": entry.client_full_name,
            "legal_entity": entry.legal_entity,
            "counter_number": entry.counter_number,
            "water_type": entry.water_type,
            "price": entry.price,
            "status": entry.status,
            "additional_info": entry.additional_info,
            "dispatcher": {
                "last_name": entry.dispatcher.last_name,
                "name": entry.dispatcher.name,
                "patronymic": entry.dispatcher.patronymic
            } if entry.dispatcher else None,
            "route": {"name": entry.route.name} if entry.route else None,
        }
        serialized.append(row)
    return serialized


def create_calendar_df(order_entries, field_list, include_no_date):
    field_set = set(field_list)
    rows = []

    for order in order_entries:
        row = {}
        is_no_date = order.get("no_date", False)

        if "date" in field_set and order.get("date"):
            row["date"] = order["date"].strftime("%d.%m.%Y")

        if "date_of_get" in field_set and order.get("date_of_get"):
            row["date_of_get"] = order["date_of_get"].strftime(
                "%d.%m.%Y %H:%M"
            )

        if "dispatcher" in field_set and order.get("dispatcher"):
            disp = order["dispatcher"]
            row["dispatcher"] = (
                f"{disp['last_name']} {disp['name']} "
                f"{disp['patronymic']}"
            )

        if "route" in field_set and order.get("route"):
            row["route"] = order["route"]["name"]

        if "address" in field_set:
            row["address"] = order.get("address") or ""

        if "phone_number" in field_set:
            row["phone_number"] = order.get("phone_number") or ""
        if "sec_phone_number" in field_set:
            row["sec_phone_number"] = order.get("sec_phone_number") or ""

        if "client_full_name" in field_set:
            row["client_full_name"] = order.get("client_full_name") or ""

        if "legal_entity" in field_set and order.get("legal_entity"):
            row["legal_entity"] = map_verification_legal_entity_to_label.get(
                order["legal_entity"], ""
            )

        if "counter_number" in field_set:
            row["counter_number"] = order.get("counter_number")

        if "water_type" in field_set and order.get("water_type"):
            row["water_type"] = map_order_water_type_to_label.get(
                order["water_type"], ""
            )

        if "price" in field_set:
            price = order.get("price")
            row["price"] = price if price is not None else ""

        if "status" in field_set:
            if is_no_date and order.get("status"):
                row["status"] = map_order_status_to_label.get(order["status"], "")
            else:
                row["status"] = ""

        if "additional_info" in field_set:
            additional_info = order.get("additional_info") or ""
            if additional_info:
                row["additional_info"] = additional_info.replace("* ", "\n")
            else:
                row["additional_info"] = ""

        rows.append({k: v for k, v in row.items() if k in field_set})

    df = pd.DataFrame(rows, columns=field_list)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(
            df["date"], errors="coerce", dayfirst=True
        )
        df.sort_values(by="date", inplace=True)
        df["date"] = df["date"].dt.strftime("%d.%m.%Y")

    df = df.fillna('').replace('', '', regex=False)

    if not include_no_date and "status" in df.columns:
        df = df.drop(columns=["status"])
        field_list = [f for f in field_list if f != "status"]

    ordered_columns = [col for col in field_list if col in df.columns]
    df = df[ordered_columns]

    df.insert(0, "№ п/п", range(1, len(df) + 1))

    df = df.rename(columns=CALENDAR_COLUMN_NAME_MAP)

    return df


@reports_dynamic_api_router.get("/list")
async def get_available_reports(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
    report_repo: CalendarReportRepository = Depends(
        read_calendar_report_repository
    )
):
    status = employee_data.status

    available_reports_models = await report_repo.get_reports_by_status(
        status
    )

    available_reports = []
    for report in available_reports_models:
        available_reports.append({
            "id": report.id,
            "name": report.name,
            "fields_order": report.fields_order or "",
            "for_auditor": report.for_auditor,
            "for_dispatcher1": report.for_dispatcher1,
            "for_dispatcher2": report.for_dispatcher2,
            "no_date": report.no_date,
            "created_at": (
                report.created_at.isoformat() if report.created_at else None
            ),
            "updated_at": (
                report.updated_at.isoformat() if report.updated_at else None
            ),
        })

    return available_reports


@reports_dynamic_api_router.get("/")
async def xlsx_dynamic_calendar_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    report_id: int = Query(..., ge=1, le=settings.max_int),
    filters: DynamicReportFilters = Depends(),
    employee_data: JwtData = Depends(check_calendar_access),
    report_repo: CalendarReportRepository = Depends(
        read_calendar_report_repository
    )
):
    status = employee_data.status

    calendar_report = await report_repo.get_report_config(report_id)
    if not calendar_report:
        raise HTTPException(
            status_code=404,
            detail="Выбранный отчет не найден."
        )

    if status in settings.AUDITOR_DISPATCHERS:
        has_access = False
        if status == EmployeeStatus.auditor and calendar_report.for_auditor:
            has_access = True
        elif (status == EmployeeStatus.dispatcher1 and
              calendar_report.for_dispatcher1):
            has_access = True
        elif (status == EmployeeStatus.dispatcher2 and
              calendar_report.for_dispatcher2):
            has_access = True

        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="В доступе к отчету отказано. "
                       "Вы не обладаете необходимым доступом."
            )

    order_entries = await report_repo.get_dynamic_report_entries(
        report_config=calendar_report,
        start_date=filters.start_date,
        end_date=filters.end_date,
        employee_id=filters.employee_id
    )

    if not order_entries:
        raise HTTPException(
            status_code=400,
            detail="Нет данных для генерации отчета. "
                   "Проверьте параметры фильтрации."
        )

    if not calendar_report.fields_order:
        raise HTTPException(
            status_code=400,
            detail=f"Отчет не содержит полей. "
            f"fields_order={calendar_report.fields_order}"
        )

    field_list = [
        f.strip() for f in calendar_report.fields_order.split(',')
        if f.strip()
    ]

    if not field_list:
        raise HTTPException(
            status_code=400,
            detail=f"После парсинга список пуст. "
                   f"Исходное: {calendar_report.fields_order}"
        )

    serialized_entries = await serialize_calendar_entries(order_entries)

    calendar_df = await run_cpu_bounds_task(
        create_calendar_df,
        serialized_entries,
        field_list,
        calendar_report.no_date
    )

    buffer = BytesIO()
    writer = pd.ExcelWriter(buffer, engine="xlsxwriter")

    sheet_name = "Календарный отчет"
    calendar_df.to_excel(writer, sheet_name=sheet_name, index=False)

    worksheet = writer.sheets[sheet_name]
    wrap_format = writer.book.add_format({'text_wrap': True})

    if "Доп. информация" in calendar_df.columns:
        col_idx = calendar_df.columns.get_loc("Доп. информация")
        worksheet.set_column(col_idx, col_idx, 50, wrap_format)

    autofit_columns(writer, calendar_df, sheet_name)

    writer.close()
    buffer.seek(0)

    filename = (
        f"Календарный отчет {calendar_report.name} "
        f"от {date_utc_now().strftime('%d-%m-%Y')}.xlsx"
    )
    encoded_filename = quote(filename)

    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f"inline; filename*=utf-8''{encoded_filename}"
            )
        }
    )
