import io
from enum import StrEnum
import zipstream
import pandas as pd
from math import inf
from urllib.parse import quote
from datetime import date as date_

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from sqlalchemy import asc, func, or_, tuple_, select, cast, Date as SADate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from access_control import (
    JwtData,
    dispatchers_exception,
)

from infrastructure.db import async_db_session

from models import (
    EmployeeModel,
    RouteModel,
    OrderModel,
    AppealModel,
    RouteEmployeeAssignmentModel,
    RouteAdditionalModel
)
from models.enums import map_verification_water_type_to_label
from models.associations import (
    employees_companies, employees_routes, employees_cities
)

from core.config import settings
from core.utils.cpu_bounds_runner import run_cpu_bounds_task
from core.reports.route_orders_report import create_report_route_orders_list


reports_static_api_router = APIRouter(
    prefix="/api/reports/static"
)


class Source(StrEnum):
    date = "date"
    date_of_get = "date_of_get"


def create_dispatchers_excel(rows, header_text):
    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        sheet_name = "Статистика по сотрудникам"
        df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=2)
        worksheet = writer.sheets[sheet_name]

        ncols = max(1, len(df.columns))
        header_fmt = writer.book.add_format({
            "bold": True,
            "font_size": 12,
            "align": "center",
            "valign": "vcenter"
        })
        worksheet.merge_range(0, 0, 0, ncols - 1, header_text, header_fmt)

        for idx, col in enumerate(df.columns):
            series = df[col].astype(str)
            max_len = max(series.map(len).max(), len(col)) + 2
            max_len = min(max_len, 50)
            worksheet.set_column(idx, idx, max_len)

    buffer.seek(0)
    return buffer


def create_orders_excel(rows):
    columns = [
        "№", "Дата", "Город", "Адрес", "Телефон и доп. телефон",
        "Кол-во счетчиков", "Заказчик", "Доп. информация",
        "Создатель заявки", "Дата и время создания",
        "Дата и время удаления"
    ]
    df = pd.DataFrame(rows, columns=columns)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        sheet = "Отчёт по заявкам"
        df.to_excel(writer, index=False, sheet_name=sheet)
        ws = writer.sheets[sheet]

        wrap_format = writer.book.add_format({'text_wrap': True})

        for idx, col in enumerate(df.columns):
            series = df[col].astype(str)
            max_len = max(series.map(len).max(), len(col)) + 2

            if col in ["Адрес", "Доп. информация"]:
                max_len = min(max_len, 40)
                ws.set_column(idx, idx, max_len, wrap_format)
            else:
                max_len = min(max_len, 50)
                ws.set_column(idx, idx, max_len)
    buf.seek(0)
    return buf


def autofit_columns(worksheet, df: pd.DataFrame):
    for idx, col in enumerate(df.columns):
        series = df[col].astype(str)
        max_len = max(series.map(len).max(), len(col)) + 2
        worksheet.set_column(idx, idx, max_len)


@reports_static_api_router.get(
    "/dispatchers",
    response_class=StreamingResponse,
    dependencies=[Depends(dispatchers_exception)]
)
async def api_dispatcher_statistic(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    start_date: date_ = Query(...),
    end_date: date_ = Query(...),
    source: Source = Query(Source.date),
    employee_id: int | None = Query(None),
    session: AsyncSession = Depends(async_db_session),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="Конечная дата выгрузки не должна быть меньше начальной.")

    # сотрудники компании
    base_emps = (
        select(
            EmployeeModel.id.label("emp_id"),
            EmployeeModel.last_name,
            EmployeeModel.name,
            EmployeeModel.patronymic,
            EmployeeModel.username,
        )
        .where(
            EmployeeModel.status.in_(settings.ACCESS_CALENDAR),
            EmployeeModel.companies.any(
                employees_companies.c.company_id == company_id),
        )
    )
    if employee_id is not None:
        base_emps = base_emps.where(EmployeeModel.id == employee_id)
    base_emps = base_emps.subquery()

    # агрегаты по заказам
    if source == Source.date:
        orders_where_period = OrderModel.date.between(start_date, end_date)
        days_expr = OrderModel.date  # уже Date
    else:  # Source.date_of_get
        orders_where_period = cast(
            OrderModel.date_of_get, SADate).between(start_date, end_date)
        days_expr = cast(OrderModel.date_of_get, SADate)

    orders_subq = (
        select(
            OrderModel.dispatcher_id.label("emp_id"),
            func.count(func.distinct(days_expr)).label("days_count"),
            func.count().label("order_count"),
            func.coalesce(func.sum(OrderModel.counter_number),
                          0).label("counters_sum"),
        )
        .where(
            OrderModel.company_id == company_id,
            OrderModel.is_active.is_(True),
            OrderModel.deleted_at.is_(None),
            orders_where_period,
        )
        .group_by(OrderModel.dispatcher_id)
        .subquery()
    )

    # агрегаты по УДАЛЁННЫМ заказам за тот же период
    orders_deleted_subq = (
        select(
            OrderModel.dispatcher_id.label("emp_id"),
            func.count().label("deleted_order_count"),
            func.coalesce(func.sum(OrderModel.counter_number),
                          0).label("deleted_counters_sum"),
        )
        .where(
            OrderModel.company_id == company_id,
            OrderModel.is_active.isnot(True),
            OrderModel.deleted_at.is_not(None),
            orders_where_period,
        )
        .group_by(OrderModel.dispatcher_id)
        .subquery()
    )

    # агрегаты по обращениям (всегда по date_of_get::date)
    appeals_subq = (
        select(
            AppealModel.dispatcher_id.label("emp_id"),
            func.count().label("appeals_count"),
        )
        .where(
            AppealModel.company_id == company_id,
            cast(AppealModel.date_of_get, SADate).between(
                start_date, end_date),
        )
        .group_by(AppealModel.dispatcher_id)
        .subquery()
    )

    # финальный запрос
    stmt = (
        select(
            base_emps.c.emp_id,
            base_emps.c.last_name,
            base_emps.c.name,
            base_emps.c.patronymic,
            base_emps.c.username,
            func.coalesce(orders_subq.c.days_count, 0).label("days_count"),
            func.coalesce(orders_subq.c.order_count, 0).label("order_count"),
            func.coalesce(orders_subq.c.counters_sum, 0).label("counters_sum"),
            func.coalesce(appeals_subq.c.appeals_count,
                          0).label("appeals_count"),
            func.coalesce(orders_deleted_subq.c.deleted_order_count, 0).label(
                "deleted_order_count"),
            func.coalesce(orders_deleted_subq.c.deleted_counters_sum, 0).label(
                "deleted_counters_sum"),
        )
        .select_from(base_emps)
        .outerjoin(
            orders_subq,
            orders_subq.c.emp_id == base_emps.c.emp_id)
        .outerjoin(
            appeals_subq,
            appeals_subq.c.emp_id == base_emps.c.emp_id)
        .outerjoin(
            orders_deleted_subq,
            orders_deleted_subq.c.emp_id == base_emps.c.emp_id)
        .order_by(
            asc(base_emps.c.last_name),
            asc(base_emps.c.name),
            asc(base_emps.c.patronymic),
        )
    )

    result = await session.execute(stmt)

    rows: list[dict] = []
    for (
        _emp_id,
        last_name,
        name,
        patronymic,
        username,
        days_count,
        order_count,
        counters_sum,
        appeals_count,
        deleted_order_count,
        deleted_counters_sum,
    ) in result:
        fio = " ".join(p for p in [
            (last_name or "").title(),
            (name or "").title(),
            (patronymic or "").title(),
        ] if p)
        rows.append({
            "Сотрудник": f"{fio} ({username})",
            "Кол-во отработанных дней": int(days_count),
            "Кол-во принятых заявок": int(order_count),
            "Кол-во счетчиков всего": int(counters_sum),
            "Кол-во принятых обращений": int(appeals_count),
            "Кол-во удаленных заявок": int(deleted_order_count),
            "Кол-во удаленных счетчиков всего": int(deleted_counters_sum),
        })

    rus_start_header = start_date.strftime("%d.%m.%Y")
    rus_end_header = end_date.strftime("%d.%m.%Y")
    filter_hint = (
        "фильтрация по дате исполнения заявок"
        if source == Source.date
        else "фильтрация по дате создания заявок"
    )
    header_text = (
        f"Статистика по сотрудникам за период "
        f"от {rus_start_header} до {rus_end_header} ({filter_hint})"
    )

    buffer = await run_cpu_bounds_task(
        create_dispatchers_excel, rows, header_text
    )

    rus_start = start_date.strftime("%d-%m-%Y")
    rus_end = end_date.strftime("%d-%m-%Y")
    source_label = 'date' if source == Source.date else 'date_of_get'
    filename = (
        f"Статистика по сотрудникам за {rus_start}–{rus_end} "
        f"({source_label}).xlsx"
    )
    encoded = quote(filename)
    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"inline; filename*=utf-8''{encoded}"},
    )


@reports_static_api_router.get(
    "/orders",
    response_class=StreamingResponse,
)
async def api_order_statistic(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    start_date: date_ = Query(...),
    end_date: date_ = Query(...),
    route_id: int | None = Query(None),
    no_data: bool = Query(False),
    employee_data: JwtData = Depends(dispatchers_exception),
    session: AsyncSession = Depends(async_db_session),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="Конечная дата выгрузки не должна быть меньше начальной.")

    # маршруты, к которым есть доступ
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    if route_id and employee_route_ids and route_id not in employee_route_ids:
        raise HTTPException(404, "У вас нет доступа к этому маршруту")

    # города сотрудника
    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    # собираем условия
    conditions = [OrderModel.company_id == company_id]

    # дата: либо по диапазону, либо допускаем no_date = True
    if no_data:
        conditions.append(
            or_(
                OrderModel.date.between(start_date, end_date),
                OrderModel.no_date.is_(True),
            )
        )
    else:
        conditions.append(OrderModel.date.between(start_date, end_date))

    # ограничение по маршрутам: доступные + необвязанные (NULL)
    if employee_route_ids:
        conditions.append(
            or_(
                OrderModel.route_id.in_(employee_route_ids),
                OrderModel.route_id.is_(None),
            )
        )

    # фильтр по конкретному маршруту, если передан
    if route_id:
        conditions.append(OrderModel.route_id == route_id)

    # фильтр по городам сотрудника (если есть)
    if employee_city_ids:
        conditions.append(OrderModel.city_id.in_(employee_city_ids))

    orders_q = (
        select(OrderModel)
        .where(*conditions)
        .options(
            selectinload(OrderModel.city),
            selectinload(OrderModel.dispatcher),
        )
        .order_by(
            asc(OrderModel.date),
            asc(OrderModel.route_id),
        )
    )

    result = await session.execute(orders_q)
    orders = result.scalars().all()

    rows: list[dict] = []
    for idx, o in enumerate(orders, start=1):
        phones = o.phone_number or ""
        if o.sec_phone_number:
            phones = f"{phones}; {o.sec_phone_number}"
        creator = ""
        if o.dispatcher:
            creator = " ".join([
                o.dispatcher.last_name.title(),
                o.dispatcher.name.title(),
                o.dispatcher.patronymic.title()
            ]) + f" ({o.dispatcher.username})"

        date_of_get_str = (
            o.date_of_get.strftime("%Y-%m-%d %H:%M:%S")
            if o.date_of_get else ""
        )
        deleted_at_str = (
            o.deleted_at.strftime("%Y-%m-%d %H:%M:%S")
            if o.deleted_at else ""
        )

        rows.append({
            "№": idx,
            "Дата": o.date.strftime("%Y-%m-%d") if o.date else "",
            "Город": o.city.name if o.city else "",
            "Адрес": o.address or "",
            "Телефон и доп. телефон": phones,
            "Кол-во счетчиков": o.counter_number or 0,
            "Заказчик": o.client_full_name or "",
            "Доп. информация": (
                o.additional_info.replace("* ", "\n")
                if o.additional_info else ""
            ),
            "Создатель заявки": creator,
            "Дата и время создания": date_of_get_str,
            "Дата и время удаления": deleted_at_str,
        })

    buf = await run_cpu_bounds_task(create_orders_excel, rows)

    rus_start = start_date.strftime("%d-%m-%Y")
    rus_end = end_date.strftime("%d-%m-%Y")
    fname = f"Статистика по заявкам за {rus_start}–{rus_end}.xlsx"
    enc = quote(fname)

    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"inline; filename*=utf-8''{enc}"}
    )


@reports_static_api_router.get(
    "/planning",
    response_class=StreamingResponse,
    dependencies=[Depends(dispatchers_exception)]
)
async def api_ordering_statistic_zipstream(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    start_date: date_ = Query(...),
    end_date: date_ = Query(...),
    verifier_id: list[int] = Query([]),
    session: AsyncSession = Depends(async_db_session),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="Конечная дата выгрузки не должна быть меньше начальной.")

    q = (
        select(EmployeeModel)
        .join(EmployeeModel.assignments)
        .where(
            EmployeeModel.default_verifier_id.isnot(None),
            EmployeeModel.is_active.is_(True),
            EmployeeModel.companies.any(
                employees_companies.c.company_id == company_id),
            RouteEmployeeAssignmentModel.date.between(start_date, end_date)
        )
        .options(
            selectinload(EmployeeModel.assignments)
            .selectinload(RouteEmployeeAssignmentModel.route)
            .selectinload(RouteModel.orders)
            .selectinload(OrderModel.city),

            with_loader_criteria(
                RouteEmployeeAssignmentModel,
                RouteEmployeeAssignmentModel.date.between(
                    start_date, end_date),
                include_aliases=True
            )
        )
        .order_by(
            EmployeeModel.last_name, EmployeeModel.name,
            EmployeeModel.patronymic)
    )
    if verifier_id:
        q = q.where(EmployeeModel.id.in_(verifier_id))

    result = await session.execute(q)
    employees = result.unique().scalars().all()

    route_date_pairs = {
        (assign.route_id, assign.date)
        for emp in employees
        for assign in getattr(emp, "assignments", [])
    }
    additional_map: dict[tuple[int, date_], str] = {}
    if route_date_pairs:
        stmt_add = (
            select(
                RouteAdditionalModel.route_id,
                RouteAdditionalModel.date,
                RouteAdditionalModel.additional_info
            )
            .where(
                tuple_(RouteAdditionalModel.route_id,
                       RouteAdditionalModel.date)
                .in_(list(route_date_pairs))
            )
        )
        rows = await session.execute(stmt_add)
        for r_id, d, info in rows.all():
            additional_map[(r_id, d)] = info or ""

    serialized_reports = []
    for emp in employees:
        full_name = (
            f"{emp.last_name.title()} "
            f"{emp.name.title()} "
            f"{emp.patronymic.title()}"
        )
        folder = (
            f"{emp.last_name.title()}_"
            f"{emp.name.title()}_"
            f"{emp.patronymic.title()}"
        )
        for assign in emp.assignments:
            route = assign.route
            assign_date = assign.date

            orders = [
                o
                for o in route.orders
                if o.date == assign_date and o.is_active
            ]
            orders.sort(
                key=lambda o: (
                    o.weight is not None,
                    o.weight if o.weight is not None else -inf
                )
            )

            input_data = []
            for o in orders:
                w_type = o.water_type
                additional_info = o.additional_info or ""
                row = {
                    "address":         o.address,
                    "phone_number":    o.phone_number,
                    "sec_phone_number": o.sec_phone_number,
                    "counter_number":  o.counter_number,
                    "price":           o.price,
                    "city_name":       o.city.name,
                    "additional_info": (
                        additional_info.replace("* ", "\n")
                        if additional_info else ""
                    ),
                    "water_type": map_verification_water_type_to_label.get(
                        w_type, ""
                    ),
                }
                input_data.append(row)

            if not input_data:
                continue

            route_additional_info = additional_map.get(
                (route.id, assign_date), "")

            add_input_data = {
                "date":                assign_date,
                "route_name":          route.name,
                "employee_full_name":  full_name,
                "route_additional_info": route_additional_info,
            }

            serialized_reports.append({
                "folder": folder,
                "route_id": route.id,
                "assign_date": assign_date,
                "input_data": input_data,
                "add_input_data": add_input_data,
            })

    zs = zipstream.ZipFile(mode="w", compression=zipstream.ZIP_DEFLATED)

    for report in serialized_reports:
        buf_xlsx = await run_cpu_bounds_task(
            create_report_route_orders_list,
            report["input_data"],
            report["add_input_data"]
        )
        buf_xlsx.seek(0)
        inner_name = (
            f"{report['folder']}/route_{report['route_id']}_"
            f"{report['assign_date']:%Y-%m-%d}.xlsx"
        )
        zs.write_iter(inner_name, buf_xlsx)

    filename = (
        f"Выгрузка_заявочных_листов_"
        f"{start_date:%Y-%m-%d}_по_{end_date:%Y-%m-%d}.zip"
    )
    content_disposition = (
        "attachment;"
        f" filename*=UTF-8''{quote(filename)}"
    )

    return StreamingResponse(
        zs,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition}
    )
