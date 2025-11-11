from datetime import date as date_
from urllib.parse import quote

from fastapi import (
    APIRouter, HTTPException, status as status_code,
    Depends, Body, Query
)
from fastapi.responses import StreamingResponse

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    dispatcher2_exception,
    active_dispatcher2_exception
)

from apps.calendar_app.common import (
    _load_orders, get_or_create_route_statistic,
    lock_routes_advisory, release_slot, reserve_slot
)

from core.config import settings
from core.reports import create_report_route_orders_list
from core.exceptions import CustomHTTPException

from infrastructure.db import async_db_session, async_db_session_begin
from models import (
    EmployeeModel,
    CounterAssignmentModel,
    OrderModel,
    CompanyModel,
    RouteModel,
    RouteEmployeeAssignmentModel,
    RouteAdditionalModel
)
from models.associations import employees_companies, employees_routes
from models.enums import map_verification_water_type_to_label

from apps.calendar_app.schemas.orders_planning import (
    RouteSchema, OrderingRouteSchema, EmployeeSchema, ReorderPayload,
    OrderForOrderingSchema, RouteAssignmentSchema, RouteAssignmentUpsert,
    RouteAdditionalResponse, RouteAdditionalUpsert
)


orders_planning_api_router = APIRouter(prefix="/api/orders/planning")


@orders_planning_api_router.get(
    "/",
    response_model=list[OrderForOrderingSchema],
)
async def list_orders_for_planning(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    routes: list[int] = Query(...),
    target_date: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    order_conds = [
        OrderModel.company_id == company_id,
        OrderModel.date == target_date,
        OrderModel.is_active.is_(True),
        OrderModel.route_id.in_(routes),
    ]

    if employee_route_ids:
        order_conds.append(
            OrderModel.route_id.in_(employee_route_ids)
        )

    stmt = (
        select(OrderModel)
        .options(selectinload(OrderModel.city))
        .where(*order_conds)
    )

    db_orders = (
        await session.execute(stmt)
    ).scalars().all()

    db_orders.sort(
        key=lambda o: (
            o.weight is None, o.weight or 1, o.id
        )
    )

    return db_orders


@orders_planning_api_router.get(
    "/routes",
    response_model=list[OrderingRouteSchema],
)
async def list_routes_for_planning(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    routes: list[int] = Query(...),
    target_date: date_ = Query(...),
    employee_data: JwtData = Depends(
        dispatcher2_exception
    ),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    route_conds = [
        RouteModel.company_id == company_id,
        RouteModel.id.in_(routes),
    ]
    if employee_route_ids:
        route_conds.append(
            RouteModel.id.in_(employee_route_ids)
        )

    db_routes = (
        await session.execute(
            select(RouteModel)
            .where(*route_conds)
        )
    ).scalars().all()

    if not db_routes:
        return []

    result = []
    for r in db_routes:
        stat = await get_or_create_route_statistic(
            session, r.id, target_date, r.day_limit
        )
        busy = r.day_limit - stat.day_limit_free

        # назначенный сотрудник (если есть)
        assigned = await session.scalar(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == r.id,
                RouteEmployeeAssignmentModel.date == target_date
            )
        )

        # дополнительная информация
        add_info = await session.scalar(
            select(RouteAdditionalModel.additional_info)
            .where(
                RouteAdditionalModel.route_id == r.id,
                RouteAdditionalModel.date == target_date
            )
        )

        route_data = RouteSchema.model_validate(r).model_dump()
        route_data["busy"] = busy
        route_data["assigned_employee_id"] = assigned
        route_data["additional_info"] = add_info

        result.append(route_data)

    return [OrderingRouteSchema.model_validate(r) for r in result]


@orders_planning_api_router.get(
    "/employees",
    response_model=list[EmployeeSchema],
)
async def list_employees_for_planning(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    date: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session),
):
    stmt = (
        select(EmployeeModel)
        .where(
            EmployeeModel.companies.any(
                CompanyModel.id == company_id
            ),
            EmployeeModel.is_active.is_(True),
            EmployeeModel.default_verifier_id.isnot(None)
        )
        .order_by(
            EmployeeModel.last_name,
            EmployeeModel.name,
            EmployeeModel.patronymic
        )
    )

    emps = (
        await session.execute(stmt)
    ).scalars().all()

    assigned = await session.execute(
        select(
            RouteEmployeeAssignmentModel.employee_id
        )
        .where(
            RouteEmployeeAssignmentModel.date == date
        )
    )
    assigned_ids = set(
        assigned.scalars().all()
    )

    result = []
    for emp in emps:
        result.append({
            "id": emp.id,
            "last_name": emp.last_name,
            "name": emp.name,
            "patronymic": emp.patronymic,
            "has_assignment": emp.id in assigned_ids,
        })
    return result


@orders_planning_api_router.post("/reorder")
async def reorder_orders_in_routes(
    payload: ReorderPayload,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        active_dispatcher2_exception
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if not payload.moved_order_id:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Вы не указали опорную заявку!"
        )

    if payload.change_route:
        if payload.old_route_id is None or payload.new_route_id is None:
            raise CustomHTTPException(
                status_code=status_code.HTTP_400_BAD_REQUEST,
                company_id=company_id,
                detail="При смене маршрута вы не указали "
                "новый или старый маршрут!"
            )
    else:
        payload.old_route_id = payload.new_route_id

    if not payload.new_order_id_list:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Новый маршрут не может быть пустым!"
        )

    # Проверка доступа к маршрутам
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids and not {
                payload.old_route_id, payload.new_route_id
            }.issubset(employee_route_ids):
        raise CustomHTTPException(
            status_code=status_code.HTTP_403_FORBIDDEN,
            company_id=company_id,
            detail="Нет доступа к одному из маршрутов!"
        )

    all_ids = (payload.old_order_id_list or []) + \
        (payload.new_order_id_list or [])
    if payload.change_route and len(all_ids) != len(set(all_ids)):
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Списки заявок содержат дубликаты!"
        )

    if payload.moved_order_id not in set(all_ids):
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Опорная заявка отсутствует в переданных списках!"
        )

    # Опорная заявка
    moved_order = (
        await session.execute(
            select(OrderModel)
            .where(
                OrderModel.company_id == company_id,
                OrderModel.id == payload.moved_order_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not moved_order:
        raise CustomHTTPException(
            status_code=404,
            company_id=company_id,
            detail="Перемещаемая заявка не найдена!"
        )

    # при смене маршрута убедимся, что заявка действительно на old_route_id
    if payload.change_route and moved_order.route_id != payload.old_route_id:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="Опорная заявка не относится к старому маршруту!")

    date = moved_order.date
    if not date:
        raise CustomHTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            company_id=company_id,
            detail="У заявки отсутствует дата!"
        )

    if payload.change_route and moved_order.route_id == payload.new_route_id:
        return {"status": "ok"}

    # Advisory-локи
    route_ids = sorted(
        {rid for rid in (payload.old_route_id, payload.new_route_id) if rid})
    if route_ids:
        await lock_routes_advisory(session, route_ids, date)

    changed_route_now = (
        payload.change_route
        and payload.old_route_id != payload.new_route_id
        and moved_order.route_id == payload.old_route_id
    )
    if changed_route_now:
        try:
            await release_slot(session, payload.old_route_id, date)
            await reserve_slot(session, payload.new_route_id, date)
        except ValueError:
            raise CustomHTTPException(
                status_code=status_code.HTTP_400_BAD_REQUEST,
                company_id=company_id,
                detail="Лимит заявок на новый маршрут исчерпан!"
            )

        await session.execute(
            delete(CounterAssignmentModel)
            .where(CounterAssignmentModel.order_id == moved_order.id)
        )

        new_emp_id = await session.scalar(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == payload.new_route_id,
                RouteEmployeeAssignmentModel.date == date,
            )
        )
        if new_emp_id:
            session.add(CounterAssignmentModel(
                order_id=moved_order.id,
                employee_id=new_emp_id,
                counter_limit=moved_order.counter_number or 0,
            ))

    if payload.old_order_id_list:
        old_map = await _load_orders(
            session, company_id, date, payload.old_order_id_list)
        for idx, order_id in enumerate(payload.old_order_id_list, start=1):
            order = old_map.get(order_id)
            if not order:
                raise CustomHTTPException(
                    status_code=status_code.HTTP_400_BAD_REQUEST,
                    company_id=company_id,
                    detail=f"Заявка {order_id} не найдена"
                    " среди старого маршрута!"
                )
            order.route_id = payload.old_route_id
            order.weight = idx

    # --- обновляем заявки нового маршрута ---
    if payload.new_order_id_list:
        new_map = await _load_orders(
            session, company_id, date, payload.new_order_id_list)
        for idx, order_id in enumerate(payload.new_order_id_list, start=1):
            order = new_map.get(order_id)
            if not order:
                raise CustomHTTPException(
                    status_code=status_code.HTTP_400_BAD_REQUEST,
                    company_id=company_id,
                    detail=f"Заявка {order_id} не найдена"
                    " среди нового маршрута!"
                )
            order.route_id = payload.new_route_id
            order.weight = idx

    return {"status": "ok"}


@orders_planning_api_router.get(
    "/employees-with-assignment",
    response_model=list[RouteAssignmentSchema],
)
async def get_route_assignments(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    routes: list[int] = Query(...),
    target_date: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session),
):
    stmt = (
        select(RouteEmployeeAssignmentModel)
        .where(
            RouteEmployeeAssignmentModel.route_id.in_(routes),
            RouteEmployeeAssignmentModel.date == target_date
        )
    )
    assigns = (await session.execute(stmt)).scalars().all()
    return assigns


@orders_planning_api_router.post(
    "/employee-assignment")
async def upsert_route_assignment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    payload: RouteAssignmentUpsert = Body(...),
    employee_data: JwtData = Depends(
        active_dispatcher2_exception
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    if employee_route_ids and payload.route_id not in employee_route_ids:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Маршрут не найден!"
        )

    route = (
        await session.execute(
            select(RouteModel)
            .where(
                RouteModel.id == payload.route_id,
            )
        )
    ).scalar_one_or_none()
    if not route or route.company_id != company_id:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Маршрут не найден!"
        )

    new_emp_id = payload.employee_id
    if new_emp_id is not None:
        emp = (
            await session.execute(
                select(EmployeeModel)
                .where(
                    EmployeeModel.id == new_emp_id,
                    EmployeeModel.companies.any(
                        employees_companies.c.company_id == company_id)
                )
                .options(selectinload(EmployeeModel.companies))
            )
        ).scalar_one_or_none()
        if not emp:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Сотрудник не найден!")

    routes_to_lock = {payload.route_id}
    if new_emp_id is not None:
        other_route_ids = (
            await session.execute(
                select(RouteEmployeeAssignmentModel.route_id)
                .where(
                    RouteEmployeeAssignmentModel.employee_id == new_emp_id,
                    RouteEmployeeAssignmentModel.date == payload.date,
                    RouteEmployeeAssignmentModel.route_id != payload.route_id,
                )
            )
        ).scalars().all()
        routes_to_lock.update(other_route_ids)

    if routes_to_lock:
        await lock_routes_advisory(
            session, sorted(routes_to_lock), payload.date)

    if new_emp_id is not None:
        await session.execute(
            delete(RouteEmployeeAssignmentModel)
            .where(
                RouteEmployeeAssignmentModel.employee_id == new_emp_id,
                RouteEmployeeAssignmentModel.date == payload.date,
                RouteEmployeeAssignmentModel.route_id != payload.route_id,
            )
        )

        old_order_ids = (
            await session.execute(
                select(OrderModel.id)
                .where(
                    OrderModel.company_id == company_id,
                    OrderModel.date == payload.date,
                    OrderModel.route_id != payload.route_id,
                )
            )
        ).scalars().all()

        if old_order_ids:
            await session.execute(
                delete(CounterAssignmentModel)
                .where(
                    CounterAssignmentModel.employee_id == new_emp_id,
                    CounterAssignmentModel.order_id.in_(old_order_ids),
                )
            )

    existing = await session.scalar(
        select(RouteEmployeeAssignmentModel)
        .where(
            RouteEmployeeAssignmentModel.route_id == payload.route_id,
            RouteEmployeeAssignmentModel.date == payload.date,
        ).with_for_update()
    )
    old_emp_id = existing.employee_id if existing else None

    orders = await session.execute(
        select(OrderModel)
        .where(
            OrderModel.company_id == company_id,
            OrderModel.route_id == payload.route_id,
            OrderModel.date == payload.date,
        )
        .order_by(OrderModel.id)
        .with_for_update()
    )
    orders = orders.scalars().all()

    order_ids = [o.id for o in orders]

    if existing and new_emp_id is None:
        await session.delete(existing)
        await session.execute(
            delete(CounterAssignmentModel)
            .where(
                CounterAssignmentModel.order_id.in_(order_ids),
                CounterAssignmentModel.employee_id == old_emp_id,
            )
        )
    elif new_emp_id is not None:
        if existing:
            existing.employee_id = new_emp_id
            session.add(existing)
        else:
            session.add(
                RouteEmployeeAssignmentModel(
                    route_id=payload.route_id,
                    employee_id=new_emp_id,
                    date=payload.date,
                )
            )

        if orders:
            await session.execute(
                delete(CounterAssignmentModel)
                .where(CounterAssignmentModel.order_id.in_(order_ids))
            )

            session.add_all([
                CounterAssignmentModel(
                    order_id=o.id,
                    employee_id=new_emp_id,
                    counter_limit=o.counter_number or 0,
                )
                for o in orders if o.is_active
            ])

    return {"status": "ok"}


@orders_planning_api_router.get(
    "/route-additional",
    response_model=list[RouteAdditionalResponse],
)
async def get_route_additional(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    routes: list[int] = Query(...),
    target_date: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids:
        routes = [r for r in routes if r in employee_route_ids]
        if not routes:
            return []

    rows = await session.execute(
        select(RouteAdditionalModel)
        .join(RouteAdditionalModel.route)
        .where(
            RouteAdditionalModel.route_id.in_(routes),
            RouteAdditionalModel.date == target_date,
            RouteModel.company_id == company_id
        )
    )
    additions = rows.scalars().all()
    return [
        RouteAdditionalResponse(
            route_id=a.route_id, date=a.date, additional_info=a.additional_info
        )
        for a in additions
    ]


@orders_planning_api_router.post(
    "/route-additional",
    response_model=RouteAdditionalResponse,
)
async def upsert_route_additional(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    payload: RouteAdditionalUpsert = Body(...),
    employee_data: JwtData = Depends(
        active_dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session_begin),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids and payload.route_id not in employee_route_ids:
        raise HTTPException(
            status_code=status_code.HTTP_403_FORBIDDEN,
            detail="Нет доступа к маршруту"
        )

    route = await session.get(RouteModel, payload.route_id)
    if not route or route.company_id != company_id:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Маршрут не найден"
        )

    row = await session.scalar(
        select(RouteAdditionalModel)
        .where(
            RouteAdditionalModel.route_id == payload.route_id,
            RouteAdditionalModel.date == payload.date
        )
        .with_for_update()
    )
    if row:
        row.additional_info = payload.additional_info
    else:
        row = RouteAdditionalModel(
            route_id=payload.route_id,
            date=payload.date,
            additional_info=payload.additional_info
        )
        session.add(row)

    return RouteAdditionalResponse(
        route_id=payload.route_id,
        date=payload.date,
        additional_info=payload.additional_info
    )


@orders_planning_api_router.get(
    "/download-report-route-orders-list",
)
async def order_ordering_download(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    route_id: int = Query(..., ge=1, le=settings.max_int),
    date: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids and route_id not in employee_route_ids:
        raise HTTPException(
            status_code=status_code.HTTP_403_FORBIDDEN,
            detail="Доступ к маршруту запрещён!"
        )

    route = (
        await session.execute(
            select(RouteModel)
            .where(
                RouteModel.id == route_id,
                RouteModel.company_id == company_id)
        )
    ).scalar_one_or_none()
    if not route:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Маршрут не найден!"
        )

    employee = (
        await session.execute(
            select(EmployeeModel)
            .join(
                RouteEmployeeAssignmentModel,
                EmployeeModel.id == RouteEmployeeAssignmentModel.employee_id
            )
            .where(
                RouteEmployeeAssignmentModel.route_id == route_id,
                RouteEmployeeAssignmentModel.date == date
            )
        )
    ).scalar_one_or_none()

    if employee:
        parts = (employee.last_name, employee.name, employee.patronymic)
        full_name = " ".join(p.title() for p in parts if p)
    else:
        full_name = ""

    route_additional_info = await session.scalar(
        select(RouteAdditionalModel.additional_info).where(
            RouteAdditionalModel.route_id == route_id,
            RouteAdditionalModel.date == date
        )
    ) or ""

    orders = (
        await session.execute(
            select(OrderModel)
            .where(
                OrderModel.route_id == route_id,
                OrderModel.date == date,
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
                o.water_type, o.water_type
            )
        })

    metadata = {
        "date":               date,
        "route_name":         route.name,
        "employee_full_name": full_name,
        "route_additional_info": route_additional_info,
    }

    buf = create_report_route_orders_list(rows, metadata)
    filename = f"Путевой (заявочный) лист на {date:%Y-%m-%d}.xlsx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )
