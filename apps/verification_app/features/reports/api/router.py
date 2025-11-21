from fastapi import APIRouter, UploadFile, Depends, File, Query
from fastapi.responses import StreamingResponse
from collections import defaultdict, Counter
from io import BytesIO
import pandas as pd
from datetime import datetime, date as Date
from urllib.parse import quote

from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, load_only

from access_control import (
    JwtData,
    auditor_verifier_exception,
    verifier_exception,
    check_access_verification,
)

from infrastructure.db import async_db_session

from core.config import settings
from core.reports import autofit_columns, create_report_route_orders_list
from core.templates.jinja_filters import get_current_date_in_tz
from core.cache.company_timezone_cache import company_tz_cache
from core.utils.cpu_bounds_runner import run_cpu_bounds_task
from core.exceptions.frontend import (
    InternalServerError,
    BadRequestError,
    NotFoundError,
    ConflictError,
    ForbiddenError,
)

from models import (
    CompanyModel, RegistryNumberModel,
    VerificationEntryModel,
    RouteEmployeeAssignmentModel, RouteAdditionalModel, OrderModel,
    RouteModel
)
from models.enums import (
    EmployeeStatus,
    map_verification_water_type_to_label,
    map_verification_seal_to_label,
    map_verification_legal_entity_to_label,
)

from apps.verification_app.repositories import (
    EmployeeRepository, read_employee_repository,
    CityRepository, read_city_repository,
    ReportRepository, read_report_repository, action_report_repository,
    ActNumberRepository, read_act_number_repository,
    ActSeriesRepository, read_act_series_repository,
)
from apps.verification_app.common import (
    generate_ra_xml, generate_fund_xml
)
from apps.verification_app.schemas.reports import (
    StatisticsForm,
    FullReportForm,
    ReportActNumberForm,
    StatisticsResponse
)


reports_api_router = APIRouter(prefix='/api/reports')

COLUMN_NAME_MAP = {
    'employee_name': 'ФИО работника',
    'verification_date': 'Дата поверки',
    'city': 'Город',
    'address': 'Адрес',
    'client_name': 'Заказчик',
    'modification_name': 'Модификация СИ',
    'registry_number': '№ гос. реестра',
    'factory_number': 'Заводской номер',
    'location_name': 'Место расположения счетчика',
    'meter_info': 'Показания счетчика',
    'end_verification_date': 'Срок окончания поверки',
    'series_name': 'Серия акта',
    'act_number': '№ акта',
    'verification_result': 'Результат поверки(годен)',
    'interval': 'МПИ, лет',
    'water_type': 'Вода',
    'method_name': 'Методика',
    'si_type': 'Тип СИ',
    'seal': 'Наличие пломбы',
    'client_phone': 'Номер телефона',
    'reason_name': 'Причины непригодности',
    'legal_entity': 'Юр. лицо',
    'manufacture_year': 'Год выпуска поверяемого СИ',
    'verifier_name': 'Поверитель',
    'qh': 'Qн',
    'addres': 'Адрес клиента',
    'verification_number': "№ св-ва о поверке",
    'reference': 'Используемый эталон',
    'ra_status': 'Информация об отчетности в РА',
    'phone_number': 'Номер телефона',
    'created_at': 'Дата создания',
    'updated_at': 'Дата обновления',
}


def apply_common_transformations(df):
    """
    Применяет преобразования для enum и boolean полей.
    Использует map функции для преобразования enum значений.
    """
    if "seal" in df:
        df["seal"] = df["seal"].map(
            lambda x: map_verification_seal_to_label.get(x, x or "")
        )

    if "water_type" in df:
        df["water_type"] = df["water_type"].map(
            lambda x: map_verification_water_type_to_label.get(x, x or "")
        )

    if "legal_entity" in df:
        df["legal_entity"] = df["legal_entity"].map(
            lambda x: map_verification_legal_entity_to_label.get(x, x or "")
        )

    if "verification_result" in df:
        df["verification_result"] = df["verification_result"].replace(
            {True: "Да", False: "Нет"})

    for n in range(1, 6):
        cb_key = f"additional_checkbox_{n}"
        if cb_key in df:
            df[cb_key] = df[cb_key].replace({True: "Да", False: "Нет"})

    return df


def apply_date_transformations(df):
    """
    Применяет преобразования дат для DataFrame:
    - Конвертирует даты в datetime для сортировки
    - Сортирует по датам
    - Форматирует даты обратно в строки
    """
    date_columns = []
    if "verification_date" in df.columns:
        df["verification_date"] = pd.to_datetime(
            df["verification_date"], errors="coerce", dayfirst=True)
        date_columns.append("verification_date")

    if "end_verification_date" in df.columns:
        df["end_verification_date"] = pd.to_datetime(
            df["end_verification_date"], errors="coerce", dayfirst=True)
        date_columns.append("end_verification_date")

    if date_columns:
        df.sort_values(by=date_columns, inplace=True)

    for col in date_columns:
        df[col] = df[col].dt.strftime("%d.%m.%Y")

    return df


async def serialize_full_report_entries(entries):
    """
    Преобразует SQLAlchemy ORM объекты в обычные словари.
    ВАЖНО: async функция для корректной работы lazy loading.
    """
    serialized = []
    for entry in entries:
        row = {
            "verification_date": entry.verification_date,
            "end_verification_date": entry.end_verification_date,
            "factory_number": entry.factory_number,
            "meter_info": entry.meter_info,
            "verification_result": entry.verification_result,
            "water_type": entry.water_type.value if entry.water_type else None,
            "seal": entry.seal.value if entry.seal else None,
            "manufacture_year": entry.manufacture_year,
            "verification_number": entry.verification_number,
            "ra_status": entry.ra_status,
            "interval": entry.interval,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

        if entry.employee:
            row["employee"] = {
                "last_name": entry.employee.last_name,
                "name": entry.employee.name,
                "patronymic": entry.employee.patronymic
            }

        if entry.city:
            row["city_name"] = entry.city.name

        if entry.act_number:
            row["act_number_data"] = {
                "address": entry.act_number.address,
                "client_full_name": entry.act_number.client_full_name,
                "act_number": entry.act_number.act_number,
                "client_phone": entry.act_number.client_phone,
                "legal_entity": entry.act_number.legal_entity.value if entry.act_number.legal_entity else None,
            }

        if entry.registry_number:
            row["registry_number_data"] = {
                "registry_number": entry.registry_number.registry_number,
                "si_type": entry.registry_number.si_type
            }

        if entry.modification:
            row["modification_name"] = entry.modification.modification_name

        if entry.location:
            row["location_name"] = entry.location.name

        if entry.series:
            row["series_name"] = entry.series.name

        if entry.method:
            row["method_name"] = entry.method.name

        if entry.reason:
            row["reason_name"] = entry.reason.full_name

        if entry.verifier:
            row["verifier"] = {
                "last_name": entry.verifier.last_name,
                "name": entry.verifier.name,
                "patronymic": entry.verifier.patronymic
            }

        serialized.append(row)

    return serialized


def create_full_df(serialized_entries, company_additional, company_tz):
    """
    Создает DataFrame из сериализованных данных.
    Выполняется в ProcessPool (CPU-bound операция).
    """
    from core.utils.time_utils import format_timestamp_with_tz

    rows = []
    for entry in serialized_entries:
        row = {
            "verification_date": entry.get("verification_date"),
            "end_verification_date": entry.get("end_verification_date"),
            "factory_number": entry.get("factory_number"),
            "meter_info": entry.get("meter_info"),
            "verification_result": entry.get("verification_result"),
            "water_type": entry.get("water_type"),
            "seal": entry.get("seal"),
            "manufacture_year": entry.get("manufacture_year"),
            "verification_number": entry.get("verification_number"),
            "ra_status": entry.get("ra_status"),
            "interval": entry.get("interval"),
            "created_at": format_timestamp_with_tz(
                entry.get("created_at"), company_tz
            ),
            "updated_at": format_timestamp_with_tz(
                entry.get("updated_at"), company_tz
            ),
        }

        if "employee" in entry:
            emp = entry["employee"]
            row["employee_name"] = f"{emp['last_name']} {emp['name']} {emp['patronymic']}"

        if "city_name" in entry:
            row["city"] = entry["city_name"]

        if "act_number_data" in entry:
            act = entry["act_number_data"]
            row.update({
                "address": act["address"],
                "client_name": act["client_full_name"],
                "act_number": act["act_number"],
                "client_phone": act["client_phone"],
                "legal_entity": act["legal_entity"],
            })

        if "registry_number_data" in entry:
            reg = entry["registry_number_data"]
            row.update({
                "registry_number": reg["registry_number"],
                "si_type": reg["si_type"]
            })

        if "modification_name" in entry:
            row["modification_name"] = entry["modification_name"]

        if "location_name" in entry:
            row["location_name"] = entry["location_name"]

        if "series_name" in entry:
            row["series_name"] = entry["series_name"]

        if "method_name" in entry:
            row["method_name"] = entry["method_name"]

        if "reason_name" in entry:
            row["reason_name"] = entry["reason_name"]

        if "verifier" in entry:
            vf = entry["verifier"]
            row["verifier_name"] = f"{vf['last_name']} {vf['name']} {vf['patronymic']}"

        rows.append(row)

    df = pd.DataFrame(rows)

    base_fields = [
        "employee_name", "verification_date", "city", "address", "client_name",
        "modification_name", "registry_number", "factory_number",
        "location_name", "meter_info", "end_verification_date", "series_name",
        "act_number", "seal", "client_phone", "water_type", "interval",
        "verification_result"
    ]
    additional_fields = []
    for n in range(1, 6):
        cb_key = f"additional_checkbox_{n}"
        in_key = f"additional_input_{n}"
        if company_additional.get(cb_key):
            additional_fields.append(cb_key)
        if company_additional.get(in_key):
            additional_fields.append(in_key)

    extended_fields = [
        "verification_number", "verifier_name", "si_type", "method_name",
        "manufacture_year", "legal_entity", "ra_status", "reason_name",
    ]
    timestamp_fields = ["created_at", "updated_at"]
    field_list_full = (
        base_fields + additional_fields + extended_fields + timestamp_fields
    )

    for n in range(1, 6):
        key_cb = f"additional_checkbox_{n}"
        key_in = f"additional_input_{n}"

        if not company_additional.get(key_cb) and key_cb in df.columns:
            df.drop(columns=[key_cb], inplace=True)

        if not company_additional.get(key_in) and key_in in df.columns:
            df.drop(columns=[key_in], inplace=True)

    df = apply_common_transformations(df)

    df = apply_date_transformations(df)

    for col in field_list_full:
        if col not in df.columns:
            df[col] = None

    ordered_columns = [col for col in field_list_full if col in df.columns]
    df = df[ordered_columns]
    df.insert(0, "№ п/п", range(1, len(df) + 1))

    df.rename(
        columns=COLUMN_NAME_MAP | dict(company_additional), inplace=True)

    df = df.replace({None: '', '': ''})

    df.reset_index(drop=True, inplace=True)

    return df


@reports_api_router.get("/full/")
async def xlsx_full_report(
    full_report_data: FullReportForm = Depends(),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(verifier_exception),
    report_repo: ReportRepository = Depends(read_report_repository)
):
    """
    Генерирует полный отчет по поверкам в формате Excel.
    Все операции с БД инкапсулированы в репозиторий.
    """
    try:
        company_tz = await company_tz_cache.get_timezone(company_id)

        verification_entries = await report_repo.get_full_report_entries(
            full_report_data
        )

        if not verification_entries:
            raise BadRequestError(
                company_id=company_id,
                detail=(
                    "Нет данных для генерации отчета. "
                    "Проверьте параметры фильтрации."
                )
            )

        company_additional = await report_repo.get_company_additional_fields()

        serialized_entries = await serialize_full_report_entries(
            verification_entries
        )

        company_additional_dict = {
            k: getattr(company_additional, k, None)
            for k in dir(company_additional)
            if not k.startswith('_')
        }

        full_df = await run_cpu_bounds_task(
            create_full_df, serialized_entries, company_additional_dict, company_tz
        )

        buffer = BytesIO()
        writer = pd.ExcelWriter(buffer, engine='xlsxwriter')
        full_df.to_excel(
            writer, sheet_name='Общий отчет компании', index=False
        )

        autofit_columns(writer, full_df, 'Общий отчет компании')

        writer.close()
        buffer.seek(0)
        current_date = get_current_date_in_tz(company_tz)
        filename = f"Общий отчет компании от {
            current_date.strftime('%d-%m-%Y')}.xlsx"
        encoded_filename = quote(filename)
        return StreamingResponse(
            buffer,
            media_type="application/"
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"inline; filename*=utf-8''{encoded_filename}"
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


async def serialize_dynamic_report_entries(entries):
    serialized = []
    for entry in entries:
        row = {
            "verification_date": entry.verification_date,
            "end_verification_date": entry.end_verification_date,
            "factory_number": entry.factory_number,
            "meter_info": entry.meter_info,
            "verification_result": entry.verification_result,
            "water_type": entry.water_type.value if entry.water_type else None,
            "seal": entry.seal.value if entry.seal else None,
            "manufacture_year": entry.manufacture_year,
            "verification_number": entry.verification_number,
            "interval": entry.interval,
            "employee": {
                "last_name": entry.employee.last_name,
                "name": entry.employee.name,
                "patronymic": entry.employee.patronymic
            } if entry.employee else None,
            "city": {"name": entry.city.name} if entry.city else None,
            "act_number": {
                "address": entry.act_number.address,
                "client_full_name": entry.act_number.client_full_name,
                "act_number": entry.act_number.act_number,
                "client_phone": entry.act_number.client_phone,
            } if entry.act_number else None,
            "registry_number": {
                "registry_number": entry.registry_number.registry_number,
                "si_type": entry.registry_number.si_type
            } if entry.registry_number else None,
            "modification": {
                "modification_name": entry.modification.modification_name
            } if entry.modification else None,
            "location": {"name": entry.location.name} if entry.location else None,
            "series": {"name": entry.series.name} if entry.series else None,
            "method": {"name": entry.method.name} if entry.method else None,
            "reason": {"full_name": entry.reason.full_name} if entry.reason else None,
            "verifier": {
                "last_name": entry.verifier.last_name,
                "name": entry.verifier.name,
                "patronymic": entry.verifier.patronymic
            } if entry.verifier else None,
            "metrolog": {"qh": entry.metrolog.qh} if entry.metrolog else None,
            "equipments": [
                {
                    "type": eq.type.value if eq.type else None,
                    "list_number": eq.list_number
                } for eq in entry.equipments
            ] if entry.equipments else [],
        }
        for n in range(1, 6):
            row[f"additional_checkbox_{n}"] = getattr(
                entry, f"additional_checkbox_{n}", None)
            row[f"additional_input_{n}"] = getattr(
                entry, f"additional_input_{n}", None)
        serialized.append(row)
    return serialized


def create_dynamic_df(
        information_query, field_list, company_additional):
    df = pd.DataFrame(columns=field_list)
    field_set = set(field_list)

    for entry in information_query:
        row_info = {}

        if "verification_date" in field_set and entry.get("verification_date"):
            row_info["verification_date"] = entry["verification_date"].strftime(
                '%d.%m.%Y')
        if "end_verification_date" in field_set and entry.get("end_verification_date"):
            row_info["end_verification_date"] = entry["end_verification_date"].strftime(
                '%d.%m.%Y')
        if "factory_number" in field_set:
            row_info["factory_number"] = entry.get("factory_number")
        if "meter_info" in field_set:
            row_info["meter_info"] = entry.get("meter_info")
        if "verification_result" in field_set:
            row_info["verification_result"] = entry.get("verification_result")
        if "water_type" in field_set:
            row_info["water_type"] = entry.get("water_type")
        if "seal" in field_set:
            row_info["seal"] = entry.get("seal")
        if "manufacture_year" in field_set:
            row_info["manufacture_year"] = entry.get("manufacture_year")
        if "verification_number" in field_set:
            row_info["verification_number"] = entry.get("verification_number")
        if "interval" in field_set:
            row_info["interval"] = entry.get("interval")
        if "qh" in field_set and entry.get("metrolog"):
            row_info["qh"] = entry["metrolog"]["qh"]
        if "employee_name" in field_set and entry.get("employee"):
            emp = entry["employee"]
            row_info["employee_name"] = f"{emp['last_name']} {emp['name']} {emp['patronymic']}"
        if "city" in field_set and entry.get("city"):
            row_info["city"] = entry["city"]["name"]
        if "address" in field_set and entry.get("act_number"):
            row_info["address"] = entry["act_number"]["address"]
        if "client_name" in field_set and entry.get("act_number"):
            row_info["client_name"] = entry["act_number"]["client_full_name"]
        if "act_number" in field_set and entry.get("act_number"):
            row_info["act_number"] = entry["act_number"]["act_number"]
        if "phone_number" in field_set and entry.get("act_number"):
            row_info["phone_number"] = entry["act_number"]["client_phone"]
        if "registry_number" in field_set and entry.get("registry_number"):
            row_info["registry_number"] = entry["registry_number"]["registry_number"]
            if "si_type" in field_set:
                row_info["si_type"] = entry["registry_number"]["si_type"]
        if "modification_name" in field_set and entry.get("modification"):
            row_info["modification_name"] = entry["modification"]["modification_name"]
        if "location_name" in field_set and entry.get("location"):
            row_info["location_name"] = entry["location"]["name"]
        if "series_name" in field_set and entry.get("series"):
            row_info["series_name"] = entry["series"]["name"]
        if "method_name" in field_set and entry.get("method"):
            row_info["method_name"] = entry["method"]["name"]
        if "reason_name" in field_set and entry.get("reason"):
            row_info["reason_name"] = entry["reason"]["full_name"]
        if "verifier_name" in field_set and entry.get("verifier"):
            ver = entry["verifier"]
            row_info["verifier_name"] = f"{ver['last_name']} {ver['name']} {ver['patronymic']}"
        if "reference" in field_set and entry.get("equipments"):
            for equipment in entry["equipments"]:
                if equipment.get("type") == "standard":
                    row_info["reference"] = equipment.get("list_number")
                    break

        for n in range(1, 6):
            cb_key = f"additional_checkbox_{n}"
            in_key = f"additional_input_{n}"

            if cb_key in field_set:
                row_info[cb_key] = entry.get(cb_key)
            if in_key in field_set:
                row_info[in_key] = entry.get(in_key)

        df = df._append({k: v for k, v in row_info.items() if k in field_set},
                        ignore_index=True)

    df = apply_common_transformations(df)
    df = apply_date_transformations(df)
    df = df.replace({None: '', '': ''})

    allowed_keys = {f"additional_input_{i}" for i in range(
        1, 6)} | {f"additional_checkbox_{i}" for i in range(1, 6)}
    rename_map = {k: v for k, v in company_additional.items()
                  if k in allowed_keys and v}

    ordered_columns = [col for col in field_list if col in df.columns]
    df = df[ordered_columns]
    df.insert(0, "№ п/п", range(1, len(df) + 1))

    df = df.rename(columns=COLUMN_NAME_MAP | rename_map)

    return df


@reports_api_router.get("/dynamic/")
async def xlsx_dynamic_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    report_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_access_verification),
    dynamic_report_data: FullReportForm = Depends(),
    report_repo: ReportRepository = Depends(read_report_repository)
):
    """
    Генерирует динамический (настраиваемый) отчет.
    Загружает только те поля из БД, которые указаны в конфигурации отчета.
    """
    try:
        company_tz = await company_tz_cache.get_timezone(company_id)

        status = employee_data.status
        empl_id = employee_data.id

        verification_report = await report_repo.get_dynamic_report_config(
            report_id
        )
        if not verification_report:
            raise NotFoundError(
                company_id=company_id,
                detail="Выбранный отчет отсутствует в компании!"
            )

        if status == EmployeeStatus.verifier:
            if not verification_report.for_verifier:
                raise ForbiddenError(
                    company_id=company_id,
                    detail=(
                        "В доступе к отчету отказано. "
                        "Вы не обладаете необходимым доступом."
                    )
                )
            employee_filter_id = empl_id
        elif status == EmployeeStatus.auditor:
            if not verification_report.for_auditor:
                raise ForbiddenError(
                    company_id=company_id,
                    detail=(
                        "В доступе к отчету отказано. "
                        "Вы не обладаете необходимым доступом."
                    )
                )
            employee_filter_id = None
        else:
            employee_filter_id = None

        company_additional = await report_repo.get_company_additional_fields()

        information_entries = await report_repo.get_dynamic_report_entries(
            report_config=verification_report,
            filter_data=dynamic_report_data,
            employee_filter_id=employee_filter_id
        )

        if not information_entries:
            raise NotFoundError(
                status_code=400,
                company_id=company_id,
                detail=(
                    "Нет данных для генерации отчета. "
                    "Проверьте параметры фильтрации."
                )
            )

        if not verification_report.fields_order:
            raise BadRequestError(
                company_id=company_id,
                detail="Отчет не содержит полей!"
            )

        field_list = [
            f.strip() for f in verification_report.fields_order.split(',')
            if f.strip()
        ]

        if not field_list:
            raise BadRequestError(
                company_id=company_id,
                detail="Отчет не содержит полей!"
            )

        serialized_entries = await serialize_dynamic_report_entries(
            information_entries
        )

        dynamic_df = await run_cpu_bounds_task(
            create_dynamic_df, serialized_entries, field_list,
            company_additional
        )

        buffer = BytesIO()
        writer = pd.ExcelWriter(buffer, engine="xlsxwriter")
        dynamic_df.to_excel(
            writer, sheet_name="Настраиваемый отчет компании", index=False
        )
        autofit_columns(writer, dynamic_df, "Настраиваемый отчет компании")

        writer.close()
        buffer.seek(0)
        current_date = get_current_date_in_tz(company_tz)
        filename = f"Отчет {verification_report.name} от {
            current_date.strftime('%d-%m-%Y')}.xlsx"
        encoded_filename = quote(filename)
        return StreamingResponse(
            buffer,
            media_type="application/"
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"inline; filename*=utf-8''{encoded_filename}"
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


async def serialize_equipment_statistics_entries(entries):
    """
    Преобразует ORM объекты в словари для статистики по эталонам.
    ВАЖНО: async функция для корректной работы lazy loading.
    """
    serialized = []
    for entry in entries:
        row = {
            "verification_date": entry.verification_date,
            "verifier": None,
            "equipments": []
        }

        if entry.verifier:
            row["verifier"] = {
                "last_name": entry.verifier.last_name
            }

        for equipment in entry.equipments:
            row["equipments"].append({
                "type": equipment.type.value if equipment.type else None,
                "factory_number": equipment.factory_number
            })

        serialized.append(row)

    return serialized


def create_standart_equipment_statistic_df(serialized_entries):
    """
    Создает DataFrame со статистикой использования эталонов по датам.
    Функция выполняется синхронно в CPU-bound пуле.
    """
    by_date = defaultdict(Counter)

    for entry in serialized_entries:
        verification_date = entry.get("verification_date")
        if not verification_date or not entry.get("verifier"):
            continue

        verifier = entry["verifier"]
        verifier_full_name = f"{verifier['last_name']}".strip()

        for equipment in entry.get("equipments", []):
            if equipment.get("type") == "standard":
                label = f"{verifier_full_name} ({equipment['factory_number']})"
                by_date[verification_date][label] += 1

    sorted_dates = sorted(by_date.keys())

    date_strs = [d.strftime('%d.%m.%Y') for d in sorted_dates]
    all_columns = sorted({col for counter in by_date.values()
                         for col in counter})

    rows = []
    for d in sorted_dates:
        row = {col: by_date[d].get(col, 0) for col in all_columns}
        rows.append(row)

    df = pd.DataFrame(
        rows,
        index=pd.Index(date_strs, name='Дата поверки'),
        columns=all_columns
    )

    df = df.replace({None: '', '': ''})

    try:
        df = df.astype(int)
    except Exception:
        pass

    return df


@reports_api_router.get("/standart-equipment-statistic/")
async def xslx_standart_equipment_statistic_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    standart_report_data: FullReportForm = Depends(),
    report_repo: ReportRepository = Depends(read_report_repository)
):
    """
    Генерирует статистику по эталонам.
    Использует оптимизированный запрос через репозиторий.
    """
    company_tz = await company_tz_cache.get_timezone(company_id)
    try:
        verification_entries = await report_repo.get_equipment_statistics_entries(
            standart_report_data
        )

        serialized_entries = await serialize_equipment_statistics_entries(
            verification_entries
        )

        counter_df = await run_cpu_bounds_task(
            create_standart_equipment_statistic_df, serialized_entries
        )

        buffer = BytesIO()
        writer = pd.ExcelWriter(buffer, engine='xlsxwriter')
        counter_df.to_excel(
            writer,
            sheet_name='Статистика по эталонам',
            index=True
        )

        autofit_columns(
            writer, counter_df, 'Статистика по эталонам', index=True
        )

        writer.close()
        buffer.seek(0)
        current_date = get_current_date_in_tz(company_tz)
        filename = f"Статистика по эталонам от {
            current_date.strftime('%d-%m-%Y')}.xlsx"
        encoded_filename = quote(filename)
        return StreamingResponse(
            buffer,
            media_type="application/"
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"attachment; filename*=utf-8''{encoded_filename}"
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


def prepare_fund_report_data(entries):
    """
    Подготавливает данные для отчета в ФИФ.
    Преобразует ORM объекты в структуру для XML шаблона.
    """
    result = []
    for entry in entries:
        info = {
            "factory_number": entry.factory_number,
            "manufacture_year": entry.manufacture_year,
            "verification_date": entry.verification_date.strftime('%Y-%m-%d'),
            "end_verification_date": (
                entry.end_verification_date.strftime('%Y-%m-%d')
            ),
            "verification_result": entry.verification_result,
            "legal_entity": (
                entry.legal_entity.value if entry.legal_entity else None
            ),
        }

        if entry.metrolog:
            info.update({
                "after_air_temperature": (
                    entry.metrolog.after_air_temperature
                ),
                "after_pressure": entry.metrolog.after_pressure,
                "after_humdity": entry.metrolog.after_humdity,
                "after_water_temperature": (
                    entry.metrolog.after_water_temperature
                ),
            })

        if entry.registry_number:
            info["registry_number"] = entry.registry_number.registry_number

        if entry.modification:
            info["modification_name"] = (
                entry.modification.modification_name
            )

        if entry.method:
            info["method_name"] = entry.method.name

        if entry.reason:
            info["reason_name"] = entry.reason.full_name

        if entry.act_number:
            info["client_full_name"] = entry.act_number.client_full_name

        info["equipments"] = []
        info["reference"] = None

        for equipment in (entry.equipments or []):
            if equipment.type and equipment.type.value == "standard":
                info["reference"] = equipment.list_number
            else:
                info["equipments"].append({
                    "registry_number": equipment.register_number,
                    "factory_number": equipment.factory_number
                })

        result.append(info)

    return result


@reports_api_router.get("/fund/")
async def xml_fund_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    fund_report_data: FullReportForm = Depends(),
    report_repo: ReportRepository = Depends(read_report_repository)
):
    """
    Генерирует XML отчет для ФИФ (Федеральный информационный фонд).
    Оптимизирован: прямая работа с ORM, без ProcessPool.
    """
    company_tz = await company_tz_cache.get_timezone(company_id)

    try:
        entries = await report_repo.get_fund_report_entries(fund_report_data)

        organization_code = await report_repo.get_organization_code() or ""

        result = prepare_fund_report_data(entries)

        xml_bytes = await run_cpu_bounds_task(
            generate_fund_xml, result, organization_code)

        current_date = get_current_date_in_tz(company_tz)
        filename = f"Отчет в ФИФ от {
            current_date.strftime('%d-%m-%Y')}.xml"
        encoded = quote(filename)

        return StreamingResponse(
            BytesIO(xml_bytes),
            media_type="application/xml",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=utf-8''{encoded}"
                )
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


def prepare_ra_report_data(entries):
    """
    Подготавливает данные для отчета в РА.
    Преобразует ORM объекты в структуру для XML шаблона.
    """
    result = []
    for entry in entries:
        info = {
            "verification_number": entry.verification_number or "",
            "verification_date": (
                entry.verification_date.strftime('%Y-%m-%d')
            ),
            "end_verification_date": (
                entry.end_verification_date.strftime('%Y-%m-%d')
            ),
            "verification_result": entry.verification_result
        }

        if entry.registry_number:
            info["si_type"] = entry.registry_number.si_type

        if entry.modification:
            info["modification_name"] = (
                entry.modification.modification_name
            )

        if entry.verifier:
            info["verifier"] = {
                "last_name": entry.verifier.last_name,
                "name": entry.verifier.name,
                "patronymic": entry.verifier.patronymic,
                "snils": entry.verifier.snils
            }

        result.append(info)

    return result


async def serialize_ra_report_entries(entries):
    """
    Преобразует ORM объекты в словари для отчета в РА.
    ВАЖНО: async функция для корректной работы lazy loading.
    Форматирует даты сразу в строки для XML.
    """
    serialized = []
    for entry in entries:
        row = {
            "verification_number": entry.verification_number or "",
            "verification_date": entry.verification_date.strftime(
                '%Y-%m-%d'
            ),
            "end_verification_date": entry.end_verification_date.strftime(
                '%Y-%m-%d'
            ),
            "verification_result": entry.verification_result
        }

        if entry.registry_number:
            row["si_type"] = entry.registry_number.si_type

        if entry.modification:
            row["modification_name"] = entry.modification.modification_name

        if entry.verifier:
            row["verifier"] = {
                "last_name": entry.verifier.last_name,
                "name": entry.verifier.name,
                "patronymic": entry.verifier.patronymic,
                "snils": entry.verifier.snils
            }

        serialized.append(row)

    return serialized


def create_ra_info_list(serialized_entries):
    """
    Подготавливает данные для отчета в РА.
    Функция выполняется синхронно в CPU-bound пуле.
    """
    result = []
    for entry in serialized_entries:
        info = {
            "verification_number": entry.get("verification_number", ""),
            "verification_date": entry["verification_date"].strftime('%Y-%m-%d'),
            "end_verification_date": entry["end_verification_date"].strftime('%Y-%m-%d'),
            "verification_result": entry.get("verification_result")
        }

        if "si_type" in entry:
            info["si_type"] = entry["si_type"]

        if "modification_name" in entry:
            info["modification_name"] = entry["modification_name"]

        if "verifier" in entry:
            v = entry["verifier"]
            info["verifier"] = {
                "last_name": v["last_name"],
                "name": v["name"],
                "patronymic": v["patronymic"],
                "snils": v["snils"]
            }

        result.append(info)

    return result


@reports_api_router.get("/ra/")
async def xml_ra_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    ra_report_data: FullReportForm = Depends(),
    report_repo: ReportRepository = Depends(action_report_repository)
):
    """
    Генерирует XML отчет для РА (Росаккредитация).
    """
    try:
        company_tz = await company_tz_cache.get_timezone(company_id)
        entries = await report_repo.get_ra_report_entries(ra_report_data)

        current_date = get_current_date_in_tz(company_tz)
        status_text = f"Отчет в РА от {
            current_date.strftime('%d-%m-%Y')}.xml"
        entry_ids = [entry.id for entry in entries]
        await report_repo.update_ra_status(entry_ids, status_text)

        serialized_entries = await serialize_ra_report_entries(entries)

        xml_bytes = await run_cpu_bounds_task(
            generate_ra_xml, serialized_entries
        )

        filename = f"Отчет в РА от {
            current_date.strftime('%d-%m-%Y')}.xml"
        encoded = quote(filename)

        return StreamingResponse(
            BytesIO(xml_bytes),
            media_type="application/xml",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=utf-8''{encoded}"
                )
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_api_router.post("/fund/")
async def xlsx_upload_fund_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(async_db_session),
    employee_data: JwtData = Depends(auditor_verifier_exception),
):
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents), skiprows=2)

        max_date = None

        for _, row in df.iterrows():
            registry_number = row['Рег. номер типа СИ']
            raw_date = row['Дата поверки']
            if isinstance(raw_date, str):
                verification_date = datetime.strptime(
                    raw_date, "%d.%m.%Y").date()
            else:
                verification_date = raw_date.date()

            factory_number = str(
                row['Заводской №/ Буквенно-цифровое обозначение'])
            verification_number = row['Документ']

            existing = (
                await session.execute(
                    select(VerificationEntryModel)
                    .join(RegistryNumberModel)
                    .where(
                        VerificationEntryModel.company_id == company_id,
                        VerificationEntryModel.factory_number == factory_number,
                        VerificationEntryModel.verification_date == verification_date,
                        RegistryNumberModel.registry_number == registry_number
                    )
                )
            ).scalars().first()

            if existing:
                existing.verification_number = verification_number

                if max_date is None or verification_date > max_date:
                    max_date = verification_date

        if max_date:
            await session.execute(
                update(CompanyModel)
                .where(CompanyModel.id == company_id)
                .where(
                    or_(
                        CompanyModel.verification_date_block.is_(None),
                        CompanyModel.verification_date_block < max_date
                    )
                )
                .values(verification_date_block=max_date)
            )

        await session.flush()
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


async def serialize_act_numbers_data(act_numbers, act_series):
    """
    Преобразует ORM объекты в простые структуры данных.
    ВАЖНО: async функция для корректной работы lazy loading.
    """
    act_numbers_list = []
    for act_number in act_numbers:
        act_numbers_list.append({
            "series_name": act_number.series.name,
            "act_number": act_number.act_number
        })

    act_series_list = []
    for series in act_series:
        act_series_list.append({
            "name": series.name
        })

    return act_numbers_list, act_series_list


def get_act_numbers_not_in_range(
    act_numbers_data, act_series_data, from_, to_
):
    """
    Создает DataFrame с отсутствующими номерами актов в указанном диапазоне.
    Функция выполняется синхронно в CPU-bound пуле.
    """
    act_number_range = {}
    for series in act_series_data:
        act_number_range[series["name"]] = set(range(from_, to_ + 1))

    for act_number in act_numbers_data:
        series_name = act_number["series_name"]
        if series_name in act_number_range:
            act_number_range[series_name].remove(act_number["act_number"])

    new_act_number_range = {}
    for key, value in act_number_range.items():
        if isinstance(value, set):
            new_act_number_range[key] = sorted(list(value))
            if len(new_act_number_range[key]) < to_:
                new_act_number_range[key] += [None] * \
                    (to_ - len(new_act_number_range[key]))
        else:
            new_act_number_range[key] = value

    df = pd.DataFrame(new_act_number_range)
    df.insert(0, 'Серия акта:', None)
    return df


@reports_api_router.get("/act-numbers/")
async def xlsx_act_number_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    report_act_number_data: ReportActNumberForm = Depends(),
    act_number_repo: ActNumberRepository = Depends(
        read_act_number_repository
    ),
    act_series_repo: ActSeriesRepository = Depends(
        read_act_series_repository
    )
):
    """
    Генерирует отчет по отсутствующим номерам актов в диапазоне.
    Использует оптимизированные репозитории.
    """
    company_tz = await company_tz_cache.get_timezone(company_id)

    try:
        if (not report_act_number_data.act_number_from or
                not report_act_number_data.act_number_to):
            raise BadRequestError(
                company_id=company_id,
                detail="Диапазон был указан неверно!"
            )

        act_numbers = await act_number_repo.get_act_numbers_in_range(
            series_id=report_act_number_data.series_id,
            act_number_from=report_act_number_data.act_number_from,
            act_number_to=report_act_number_data.act_number_to
        )

        act_series = await act_series_repo.get_series_for_report(
            series_id=report_act_number_data.series_id
        )

        act_numbers_data, act_series_data = await serialize_act_numbers_data(
            act_numbers, act_series
        )

        act_numbers_df = await run_cpu_bounds_task(
            get_act_numbers_not_in_range,
            act_numbers_data, act_series_data,
            report_act_number_data.act_number_from,
            report_act_number_data.act_number_to
        )

        buffer = BytesIO()
        writer = pd.ExcelWriter(buffer, engine='xlsxwriter')
        act_numbers_df.to_excel(
            writer,
            sheet_name='Статистика по номерами актов',
            index=False
        )

        autofit_columns(
            writer, act_numbers_df, 'Статистика по номерами актов'
        )

        writer.close()
        buffer.seek(0)
        current_date = get_current_date_in_tz(company_tz)
        filename = (
            f"Статистика по номерам актов от "
            f"{current_date.strftime('%d-%m-%Y')}.xlsx"
        )
        encoded_filename = quote(filename)
        return StreamingResponse(
            buffer,
            media_type=(
                "application/"
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": (
                    f"inline; filename*=utf-8''{encoded_filename}"
                )
            }
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_api_router.get("/orders-sheet/")
async def xlsx_orders_sheet_report(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
    order_date: Date = Query(...),
    employee_data: JwtData = Depends(
        check_access_verification
    ),
):
    try:
        employee_id = employee_data.id
        parts = (
            employee_data.last_name,
            employee_data.name,
            employee_data.patronymic)
        full_name = " ".join(p.title() for p in parts if p)

        assignment_route = (
            await session.execute(
                select(RouteEmployeeAssignmentModel)
                .where(
                    RouteEmployeeAssignmentModel.employee_id == employee_id,
                    RouteEmployeeAssignmentModel.date == order_date
                )
                .options(
                    load_only(
                        RouteEmployeeAssignmentModel.route_id
                    ),
                    selectinload(
                        RouteEmployeeAssignmentModel.route
                    ).load_only(
                        RouteModel.name
                    )
                )
            )
        ).scalar_one_or_none()
        if not assignment_route:
            raise ConflictError(
                company_id=company_id,
                detail="На выбранную дату у вас нет назначенных маршрутов!"
            )

        route_additional_info = await session.scalar(
            select(RouteAdditionalModel.additional_info).where(
                RouteAdditionalModel.route_id == assignment_route.route_id,
                RouteAdditionalModel.date == order_date
            )
        ) or ""

        orders = (
            await session.execute(
                select(OrderModel)
                .where(
                    OrderModel.route_id == assignment_route.route_id,
                    OrderModel.date == order_date,
                    OrderModel.is_active.is_(True)
                )
                .order_by(OrderModel.weight)
                .options(selectinload(OrderModel.city))
            )
        ).scalars().all()

        rows = []
        for o in orders:
            rows.append({
                "address":          o.address,
                "phone_number":     o.phone_number,
                "sec_phone_number": o.sec_phone_number,
                "counter_number":   o.counter_number,
                "price":            o.price,
                "city_name":        o.city.name,
                "additional_info":  o.additional_info,
                "water_type":       map_verification_water_type_to_label.get(
                    o.water_type, ''
                )
            })

        metadata = {
            "date":               order_date,
            "route_name":         assignment_route.route.name,
            "employee_full_name": full_name,
            "route_additional_info": route_additional_info,
        }

        buf = await run_cpu_bounds_task(
            create_report_route_orders_list, rows, metadata)
        filename = f"Путевой (заявочный) лист на {order_date:%Y-%m-%d}.xlsx"
        encoded_filename = quote(filename)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_api_router.get("/employees/", response_model=StatisticsResponse)
async def get_employees_statistics_data(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    statistic_data: StatisticsForm = Depends(),
    employee_repo: EmployeeRepository = Depends(read_employee_repository)
):
    """
    API эндпоинт для получения статистики по сотрудникам.
    Возвращает JSON с данными для отображения в таблице.
    """
    try:
        report_list = await employee_repo.get_employees_statistics(
            date_from=statistic_data.date_from,
            date_to=statistic_data.date_to
        )
        return StatisticsResponse(data=report_list)
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_api_router.get("/cities/", response_model=StatisticsResponse)
async def get_cities_statistics_data(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    statistic_data: StatisticsForm = Depends(),
    city_repo: CityRepository = Depends(read_city_repository)
):
    """
    API эндпоинт для получения статистики по городам.
    Возвращает JSON с данными для отображения в таблице.
    """
    try:
        report_list = await city_repo.get_cities_statistics(
            date_from=statistic_data.date_from,
            date_to=statistic_data.date_to
        )
        return StatisticsResponse(data=report_list)
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )
