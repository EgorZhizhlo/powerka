from typing import List
from itertools import groupby
from datetime import date as date_
from fastapi import (
    APIRouter, HTTPException, status as status_code,
    Body, Query, Depends
)
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    EmployeeModel,
    CityModel,
    RouteStatisticModel,
    OrderModel,
    CounterAssignmentModel,
    RouteModel,
    RouteEmployeeAssignmentModel,
)
from models.associations import employees_cities, employees_routes

from core.config import settings
from core.utils.time_utils import datetime_utc_now

from infrastructure.db import async_db_session, async_db_session_begin

from access_control import (
    JwtData,
    check_calendar_access,
    check_active_access_calendar
)

from apps.calendar_app.common import (
    ensure_no_duplicate_address, _assigned, lock_routes_advisory,
    release_slot, reserve_slot, get_or_create_route_statistic,
    get_calendar_order, get_route_key, sorting_key,
    check_order_limit_available, increment_order_count,
    decrement_order_count,
)

from apps.calendar_app.schemas.orders_calendar import (
    CalendarOrdersResponse,
    LowOrderSchema,
    OrderSchema,
    RouteOrdersSchema,
    CalendarOrderDetailResponse,
    OrderUpdateForm,
    OrderCreateForm,
    RouteSchema,
    CitySchema,
    EmployeeSchema,
    ReweightOrderRequest
)


orders_calendar_api_router = APIRouter(prefix="/api/orders/calendar")


@orders_calendar_api_router.get(
    "/",
    response_model=CalendarOrdersResponse)
async def list_orders_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    target_date: date_ = Query(...),
    employee_data: JwtData = Depends(check_calendar_access),
    session: AsyncSession = Depends(async_db_session),
):
    status = employee_data.status
    employee_id = employee_data.id

    orders = await get_calendar_order(
        target_date=target_date,
        session=session,
        user_status=status,
        company_id=company_id,
        dispatcher_id=employee_id,
    )
    sorted_orders = sorted(orders, key=sorting_key)

    route_ids = {o.route_id for o in sorted_orders if o.route_id is not None}
    emp_map: dict[int, EmployeeModel] = {}
    if route_ids:
        assigns = (
            await session.execute(
                select(RouteEmployeeAssignmentModel)
                .options(selectinload(RouteEmployeeAssignmentModel.employee))
                .where(
                    RouteEmployeeAssignmentModel.route_id.in_(route_ids),
                    RouteEmployeeAssignmentModel.date == target_date
                )
            )
        ).scalars().all()

        for a in assigns:
            if a.employee:
                emp_map[a.route_id] = a.employee

    result_groups: List[RouteOrdersSchema] = []
    for route_key, group in groupby(sorted_orders, key=get_route_key):
        batch = list(group)
        first = batch[0]
        rid = first.route.id if first.route else None

        # Получаем Pydantic-объект для сотрудника (если есть)
        employee_schema = (
            EmployeeSchema.model_validate(emp_map[rid])
            if rid in emp_map else None
        )

        result_groups.append(
            RouteOrdersSchema(
                route_id=rid,
                route_name=route_key or "Без маршрута",
                route_color=(
                    first.route.color
                    if first.route and first.route.color
                    else "E1E1E1"
                ),
                employee=employee_schema,
                orders=[LowOrderSchema.model_validate(o) for o in batch]
            )
        )

    return CalendarOrdersResponse(
        title=f"Меню заявок на {target_date.strftime('%Y.%m.%d')}",
        orders=result_groups
    )


@orders_calendar_api_router.get(
    "/order",
    response_model=CalendarOrderDetailResponse
)
async def order_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_calendar_access
    ),
    session: AsyncSession = Depends(async_db_session),
):
    status = employee_data.status
    employee_id = employee_data.id

    order = await get_calendar_order(
        order_id=order_id,
        session=session,
        user_status=status,
        company_id=company_id,
        dispatcher_id=employee_id,
        only_active=False
    )

    if not order:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена"
        )

    return CalendarOrderDetailResponse(
        title=f"Заявка №{order_id}",
        order=OrderSchema.model_validate(order)
    )


@orders_calendar_api_router.post(
    "/order/create", response_model=CalendarOrderDetailResponse
)
async def create_order_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    form: OrderCreateForm = Body(...),
    employee_data: JwtData = Depends(
        check_active_access_calendar
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    await check_order_limit_available(
        session=session,
        company_id=company_id,
        required_slots=1
    )

    new_order = None
    order_date = None if form.no_date else form.date
    await ensure_no_duplicate_address(
        session, company_id, form.city_id, form.address, order_date
    )

    route_id = form.route_id
    city_id = form.city_id

    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids:
        employee_route_ids.append(None)
        if route_id not in employee_route_ids:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Доступ к данному маршруту запрещен!"
            )

    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_city_ids and city_id not in employee_city_ids:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Доступ к данному городу запрещен!"
        )

    if route_id and not form.no_date and order_date:
        await lock_routes_advisory(session, [route_id], order_date)
        try:
            await reserve_slot(session, route_id, order_date)
        except ValueError:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Лимит заявок на этот маршрут исчерпан"
            )

    # Создаём заявку
    new_order = OrderModel(
        company_id=company_id,
        dispatcher_id=employee_data.id,
        **form.model_dump(exclude={"date", "no_date"}),
        date=order_date,
        no_date=form.no_date or False
    )
    session.add(new_order)
    await session.flush()

    if new_order.route_id and new_order.date:
        ver_employee_id = (
            await session.execute(
                select(RouteEmployeeAssignmentModel.employee_id)
                .where(
                    RouteEmployeeAssignmentModel.route_id == new_order.route_id,
                    RouteEmployeeAssignmentModel.date == new_order.date
                )
            )
        ).scalar_one_or_none()
        if ver_employee_id:
            session.add(
                CounterAssignmentModel(
                    order_id=new_order.id,
                    employee_id=ver_employee_id,
                    counter_limit=new_order.counter_number or 0
                )
            )

    await session.refresh(new_order, attribute_names=["city", "route"])

    await increment_order_count(
        session=session,
        company_id=company_id,
        delta=1
    )

    if new_order:
        return CalendarOrderDetailResponse(
            title=f"Заявка №{new_order.id}",
            order=OrderSchema.model_validate(new_order)
        )
    raise HTTPException(
        status_code=status_code.HTTP_400_BAD_REQUEST,
        detail="Заявка не была создана!")


@orders_calendar_api_router.put(
    "/order/update",
    response_model=CalendarOrderDetailResponse
)
async def update_order_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    form: OrderUpdateForm = Body(...),
    employee_data: JwtData = Depends(
        check_active_access_calendar
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    order = await get_calendar_order(
        order_id=order_id,
        session=session,
        user_status=employee_data.status,
        company_id=company_id,
        dispatcher_id=employee_data.id,
        for_update=True,
    )
    if not order:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена"
        )

    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_route_ids:
        allowed = employee_route_ids[:]
        allowed.append(None)
        if form.route_id not in allowed:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Доступ к данному маршруту запрещен!"
            )

    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()
    if employee_city_ids and form.city_id not in employee_city_ids:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Доступ к данному городу запрещен!"
        )

    old_route_id = order.route_id
    old_date = order.date
    old_no_date = order.no_date

    data = form.model_dump(exclude_unset=True)

    new_city_id = data.get("city_id", order.city_id)
    new_address = data.get("address", order.address)
    new_date = (
        None if data.get("no_date", order.no_date)
        else data.get("date", order.date)
    )

    await ensure_no_duplicate_address(
        session,
        company_id,
        new_city_id,
        new_address,
        new_date,
        exclude_order_id=order.id
    )
    new_no_date = data.get("no_date", old_no_date)
    new_date = data.get("date", old_date)
    new_route_id = data.get("route_id", old_route_id)

    old_pair = (old_route_id, old_date) if (
        old_route_id and old_date and not old_no_date) else None
    new_pair = (new_route_id, new_date) if (
        new_route_id and new_date and not new_no_date) else None

    if old_pair != new_pair:
        if old_pair and await _assigned(*old_pair, session=session):
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Нельзя изменить: на старую дату"
                "есть назначенный сотрудник."
            )
        if new_pair and await _assigned(*new_pair, session=session):
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Нельзя изменить: на новую дату есть"
                " назначенный сотрудник."
            )

    pairs_to_lock = []
    if old_pair:
        pairs_to_lock.append(old_pair)
    if new_pair:
        pairs_to_lock.append(new_pair)
    for rid, d in sorted(set(pairs_to_lock), key=lambda x: (x[0], x[1])):
        await lock_routes_advisory(session, [rid], d)

    if not old_no_date and new_no_date:
        if old_route_id is not None and old_date is not None:
            stat_old = await get_or_create_route_statistic(
                session, old_route_id, old_date
            )
            stat_old.day_limit_free += 1

    elif old_no_date and not new_no_date:
        if new_route_id is not None and new_date is not None:
            stat_new = await get_or_create_route_statistic(
                session, new_route_id, new_date
            )
            if stat_new.day_limit_free <= 0:
                raise HTTPException(
                    status_code=status_code.HTTP_404_NOT_FOUND,
                    detail="Лимит заявок на этот маршрут исчерпан"
                )
            stat_new.day_limit_free -= 1

    elif not old_no_date and not new_no_date:
        if old_pair != new_pair:
            if old_route_id is not None and old_date is not None:
                stat_old = await get_or_create_route_statistic(
                    session, old_route_id, old_date
                )
                stat_old.day_limit_free += 1

            if new_route_id is not None and new_date is not None:
                stat_new = await get_or_create_route_statistic(
                    session, new_route_id, new_date
                )
                if stat_new.day_limit_free <= 0:
                    raise HTTPException(
                        status_code=status_code.HTTP_404_NOT_FOUND,
                        detail="Лимит заявок на этот маршрут исчерпан"
                    )
                stat_new.day_limit_free -= 1

    order.no_date = new_no_date
    if new_no_date:
        order.date = None
    else:
        order.date = new_date

    order.route_id = new_route_id

    old_cn = order.counter_number or 0
    new_cn = data.get("counter_number", old_cn) or 0
    delta = new_cn - old_cn

    for key in ("no_date", "date", "route_id"):
        data.pop(key, None)

    for field, value in data.items():
        setattr(order, field, value)

    await session.flush()
    await session.refresh(
        order,
        attribute_names=["city", "route"])

    ver_employee_id = (
        await session.execute(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == order.route_id,
                RouteEmployeeAssignmentModel.date == order.date
            )
        )
    ).scalar_one_or_none()
    if ver_employee_id:
        counter_assignment = (
            await session.execute(
                select(CounterAssignmentModel)
                .where(
                    CounterAssignmentModel.order_id == order.id
                )
            )
        ).scalar_one_or_none()
        if not counter_assignment:
            c = CounterAssignmentModel(
                order_id=order.id,
                employee_id=ver_employee_id,
                counter_limit=order.counter_number
            )
            session.add(c)
        else:
            counter_assignment.employee_id = ver_employee_id
            counter_assignment.counter_limit += delta

    return CalendarOrderDetailResponse(
        title=f"Заявка №{order.id}",
        order=OrderSchema.model_validate(order)
    )


@orders_calendar_api_router.delete(
    "/order/delete",
    response_model=CalendarOrderDetailResponse)
async def delete_order_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_calendar
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    status = employee_data.status
    employee_id = employee_data.id

    async with session.begin():
        order = await get_calendar_order(
            order_id=order_id,
            session=session,
            user_status=status,
            company_id=company_id,
            dispatcher_id=employee_id,
            for_update=True,
        )
        if not order:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Заявка не найдена"
            )

        if order.route_id is not None and order.date is not None:
            await lock_routes_advisory(session, [order.route_id], order.date)
            await release_slot(session, order.route_id, order.date)

        await session.execute(
            delete(CounterAssignmentModel)
            .where(
                CounterAssignmentModel.order_id == order.id
            )
        )
        order.is_active = False
        order.deleted_at = datetime_utc_now()

        await decrement_order_count(
            session=session,
            company_id=company_id,
            delta=1
        )

    return CalendarOrderDetailResponse(
        title=f"Заявка №{order.id}",
        order=OrderSchema.model_validate(order)
    )


@orders_calendar_api_router.patch(
    "/actions/reweight",
    status_code=status_code.HTTP_204_NO_CONTENT
)
async def reweight_order(
    data: ReweightOrderRequest,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_calendar),
    session: AsyncSession = Depends(async_db_session_begin),
):
    unique_ids = set(data.ordered_ids)
    if len(unique_ids) != len(data.ordered_ids):
        raise HTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            detail="Список содержит повторяющиеся id."
        )

    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    allowed = employee_route_ids[:]
    if employee_data.status not in settings.DISPATCHER2:
        allowed.append(None)

    base_q = select(OrderModel).where(
        OrderModel.company_id == company_id,
        OrderModel.is_active.is_(True),
        OrderModel.id.in_(data.ordered_ids),
    )
    if employee_route_ids:
        base_q = base_q.where(OrderModel.route_id.in_(allowed))

    orders = (await session.execute(base_q)).scalars().all()

    if len(orders) != len(data.ordered_ids):
        raise HTTPException(
            status_code=400,
            detail="Некоторые заявки не найдены "
                   "или не принадлежат компании."
        )

    pairs = {(o.route_id, o.date) for o in orders}
    if len(pairs) != 1:
        raise HTTPException(
            status_code=400,
            detail="Перестановка допустима только "
                   "внутри одного маршрута и даты."
        )

    route_id, the_date = next(iter(pairs))

    if route_id is not None:
        await lock_routes_advisory(session, [route_id], the_date)

        assigned = await session.scalar(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == route_id,
                RouteEmployeeAssignmentModel.date == the_date
            )
        )
        if assigned:
            raise HTTPException(
                status_code=403,
                detail="Перемещение заявок данного маршрута "
                "невозможно: на дату есть назначенный сотрудник."
            )

    await session.execute(
        select(OrderModel)
        .where(OrderModel.id.in_(data.ordered_ids))
        .order_by(OrderModel.id)
        .with_for_update()
    )

    weight_map = {
        oid: idx
        for idx, oid in enumerate(data.ordered_ids, start=1)
    }
    mappings = [
        {"id": oid, "weight": weight_map[oid]}
        for oid in data.ordered_ids
    ]

    await session.run_sync(
        lambda s: s.bulk_update_mappings(OrderModel, mappings)
    )


@orders_calendar_api_router.patch(
    "/actions/move",
    status_code=status_code.HTTP_204_NO_CONTENT
)
async def move_order(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    new_date: date_ = Query(...),
    employee_data: JwtData = Depends(
        check_active_access_calendar
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    order = await get_calendar_order(
        order_id=order_id,
        session=session,
        user_status=employee_data.status,
        company_id=company_id,
        dispatcher_id=employee_data.id,
        for_update=True,
    )

    if not order:
        raise HTTPException(
            status_code=status_code.HTTP_404_NOT_FOUND,
            detail="Заявка не была найдена!"
        )

    old_date = order.date
    route_id = order.route_id

    # Если дата не меняется — выходим
    if old_date == new_date:
        return

    # Проверка дублей адреса на новую дату
    await ensure_no_duplicate_address(
        session,
        company_id,
        order.city_id,
        order.address,
        new_date,
        exclude_order_id=order.id
    )

    if route_id is not None:
        # Запрет при назначении на старую/новую даты
        if old_date is not None:
            assigned_old = await session.scalar(
                select(RouteEmployeeAssignmentModel.employee_id)
                .where(
                    RouteEmployeeAssignmentModel.route_id == route_id,
                    RouteEmployeeAssignmentModel.date == old_date
                )
            )
            if assigned_old:
                raise HTTPException(
                    tatus_code=status_code.HTTP_403_FORBIDDEN,
                    detail="Перемещение заявок данного маршрута невозможно: "
                           "на старую дату есть назначенный сотрудник."
                )

        assigned_new = await session.scalar(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == route_id,
                RouteEmployeeAssignmentModel.date == new_date
            )
        )
        if assigned_new:
            raise HTTPException(
                status_code=status_code.HTTP_403_FORBIDDEN,
                detail="Перемещение заявок данного маршрута невозможно:"
                       " на новую дату есть назначенный сотрудник."
            )

        # Advisory-локи на (route_id, old_date) и (route_id, new_date)
        pairs_to_lock = []
        if old_date is not None:
            pairs_to_lock.append((route_id, old_date))
        pairs_to_lock.append((route_id, new_date))
        for rid, d in sorted(pairs_to_lock, key=lambda x: (x[0], x[1])):
            await lock_routes_advisory(session, [rid], d)

    # Освобождаем старый слот (если был)
    if route_id is not None and old_date is not None:
        await release_slot(session, route_id, old_date)

    # Резервируем новый слот (если маршрут задан)
    if route_id is not None:
        try:
            await reserve_slot(session, route_id, new_date)
        except ValueError:
            raise HTTPException(
                status_code=status_code.HTTP_400_BAD_REQUEST,
                detail=f"Недостаточно свободных мест на дату {
                    new_date.strftime("%d.%m.%Y,")
                }."
            )

    # Обновляем заявку
    order.date = new_date


@orders_calendar_api_router.get(
    "/routes",
    response_model=List[RouteSchema],
)
async def list_routes(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    target_date: date_ = Query(default=None),
    employee_data: JwtData = Depends(
        check_calendar_access
    ),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    q = select(RouteModel).where(RouteModel.company_id == company_id)
    if employee_route_ids:
        q = q.where(RouteModel.id.in_(employee_route_ids))
    routes_result = await session.execute(q.order_by(RouteModel.id))

    routes = routes_result.scalars().all()
    if not routes:
        return []

    stat_by_route = {}
    if target_date:
        stat_result = await session.execute(
            select(RouteStatisticModel)
            .where(RouteStatisticModel.route_id.in_([r.id for r in routes]))
            .where(RouteStatisticModel.date == target_date)
        )
        stats = stat_result.scalars().all()
        stat_by_route = {r.route_id: r for r in stats}

        new_stats = []
        for route in routes:
            if route.id not in stat_by_route:
                new_stat = RouteStatisticModel(
                    route_id=route.id,
                    date=target_date,
                    day_limit_free=route.day_limit
                )
                session.add(new_stat)
                await session.flush()
                stat_by_route[route.id] = new_stat
                new_stats.append(new_stat)
        if new_stats:
            await session.commit()

    result = []
    for route in routes:
        stat = stat_by_route.get(route.id)
        busy = None
        if stat:
            busy = route.day_limit - stat.day_limit_free
        route_dict = RouteSchema.model_validate(route).model_dump()
        route_dict['busy'] = busy
        result.append(route_dict)
    return result


@orders_calendar_api_router.get(
    "/cities",
    response_model=List[CitySchema],
)
async def list_cities(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_calendar_access
    ),
    session: AsyncSession = Depends(async_db_session),
):
    employee_city_ids = (
        await session.execute(
            select(employees_cities.c.city_id)
            .where(employees_cities.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    q = select(CityModel).where(
        CityModel.company_id == company_id)
    if employee_city_ids:
        q = q.where(
            CityModel.id.in_(employee_city_ids))
    q = q.order_by(CityModel.name)
    result = await session.execute(q)
    cities = result.scalars().all()

    return [CitySchema.model_validate(c) for c in cities]
