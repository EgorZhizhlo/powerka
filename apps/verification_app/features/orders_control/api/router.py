import math
import json
from typing import List
from fastapi import (
    APIRouter, Response, UploadFile,
    Depends, Body, Query, File, Form
)
from fastapi import status as status_code

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.db import async_db_session_begin, async_db_session
from models import (
    OrderModel,
    CounterAssignmentModel,
    VerificationEntryModel,
    MetrologInfoModel
)
from models.enums import ReasonType

from access_control import (
    JwtData,
    check_access_verification,
    check_active_access_verification,
    admin_director
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.utils.time_utils import validate_company_timezone
from core.exceptions.api import (
    BadRequestError,
    NotFoundError,
    ForbiddenError
)

from apps.verification_app.schemas.orders_control import (
    LowOrderItemResponse, OrderFilter, OrderListResponse,
    CounterAssignmentResponse, CounterAssignmentCreateRequest
)
from apps.verification_app.schemas.verifications_control import (
    CreateVerificationEntryForm, MetrologInfoForm
)
from apps.verification_app.services import (
    process_act_number_photos,

    check_verification_limit_available,
    increment_verification_count
)
from apps.verification_app.repositories import (
    EmployeeCitiesRepository, read_employee_cities_repository,
    CompanyRepository, read_company_repository,
    VerificationEntryRepository,
    action_verification_entry_repository,
    VerifierRepository, read_verifier_repository,
    EquipmentRepository, action_equipment_repository,
    LocationRepository, action_location_repository,
    OrderRepository, read_order_repository,
)
from apps.verification_app.common import (
    check_equip_conditions, act_number_for_create, check_act_number_limit,
    get_verifier_id_create, right_automatisation_metrolog,
    clear_verification_cache,
)
from core.exceptions.api import (
    VerificationLimitError,
    VerificationVerifierError,
    VerificationEntryError,
    VerificationEquipmentError,

    CreateVerificationCitiesBlockError,
    CreateVerificationDateBlockError,
    CreateVerificationFactoryNumBlockError,
    CreateVerificationDefaultVerifierError,
)


orders_control_api_router = APIRouter(prefix='/api/orders-control')


@orders_control_api_router.get(
    "/", response_model=OrderListResponse
)
async def get_orders(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_filter: OrderFilter = Depends(),
    employee_data: JwtData = Depends(check_access_verification),
    session: AsyncSession = Depends(async_db_session),
):
    employee_id = employee_data.id

    counter_assignment_q = (
        select(CounterAssignmentModel)
        .join(CounterAssignmentModel.order)
        .options(
            selectinload(CounterAssignmentModel.order)
            .selectinload(OrderModel.city))
        .where(
            CounterAssignmentModel.employee_id == employee_id,
            OrderModel.company_id == company_id,
            OrderModel.date == order_filter.date
        )
        .order_by(OrderModel.weight)
    )
    counter_assignments = (
        await session.execute(counter_assignment_q)).scalars().all()
    total_count = sum(
        ca.counter_limit or 0
        for ca in counter_assignments
    )
    total_pages = (
        math.ceil(total_count / order_filter.limit) if total_count else 1
    )

    if order_filter.page > total_pages and total_count > 0:
        raise BadRequestError(
            detail=(
                f"Страница {order_filter.page} выходит за пределы "
                f"(макс. {total_pages})!"
            )
        )

    expanded_items: List[LowOrderItemResponse] = []
    for ca in counter_assignments:
        order = ca.order
        for _ in range(ca.counter_limit or 0):
            expanded_items.append(
                LowOrderItemResponse(
                    id=order.id,
                    address=(order.address or ""),
                    client_full_name=(order.client_full_name or ""),
                    phone_number=order.phone_number,
                    city=order.city,
                    counter_assignment_id=ca.id
                )
            )

    offset = (order_filter.page - 1) * order_filter.limit
    paged_items = expanded_items[offset: offset + order_filter.limit]

    return OrderListResponse(
        total_count=total_count,
        total_pages=total_pages,
        page=order_filter.page,
        limit=order_filter.limit,
        orders=paged_items
    )


@orders_control_api_router.post(
    "/counter-assignment/",
    response_model=CounterAssignmentResponse,
    status_code=status_code.HTTP_201_CREATED
)
async def create_counter_assignment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    payload: CounterAssignmentCreateRequest = Body(...),
    employee_data: JwtData = Depends(
        check_active_access_verification
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    employee_id = employee_data.id

    order = await session.get(OrderModel, payload.order_id)
    if not order or order.company_id != company_id:
        raise NotFoundError(
            detail="Заказ не найден или не принадлежит этой компании!"
        )

    counter_assignment = await session.execute(
        update(CounterAssignmentModel)
        .where(
            CounterAssignmentModel.order_id == order.id,
            CounterAssignmentModel.counter_limit < 10
        )
        .values(counter_limit=CounterAssignmentModel.counter_limit + 1)
    )
    if counter_assignment.rowcount == 0:
        raise BadRequestError(
            detail="Добавление новой записи невозможно!"
        )

    updated = (
        await session.execute(
            select(CounterAssignmentModel)
            .where(CounterAssignmentModel.order_id == order.id,)
        )
    ).scalar_one()

    return CounterAssignmentResponse(
        id=updated.id,
        order_id=order.id,
        counter_limit=updated.counter_limit,
        employee_id=employee_id
    )


@orders_control_api_router.delete(
    "/counter-assignment/",
    status_code=status_code.HTTP_204_NO_CONTENT
)
async def delete_counter_assignment(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    counter_assignment_id: int = Query(..., ge=1, le=settings.max_int),
    additional: str = Body(..., embed=True),
    employee_data: JwtData = Depends(
        check_active_access_verification
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    employee_id = employee_data.id

    assignment = await session.get(
        CounterAssignmentModel, counter_assignment_id
    )
    if not assignment:
        raise NotFoundError(
            detail="Запись не найдена!"
        )

    if assignment.employee_id != employee_id:
        raise ForbiddenError(
            detail="Нельзя удалять чужую запись!"
        )

    order_obj = await session.get(OrderModel, assignment.order_id)
    if not order_obj or order_obj.company_id != company_id:
        raise BadRequestError(
            detail="Несовпадение компании у заказа!"
        )

    entry_line = f"* Удаление счётчика (Причина: {additional})\n"
    order_obj.additional_info = (
        order_obj.additional_info or "") + entry_line
    await session.flush()

    result = await session.execute(
        update(CounterAssignmentModel)
        .where(
            CounterAssignmentModel.id == assignment.id,
            CounterAssignmentModel.counter_limit > 1
        )
        .values(counter_limit=CounterAssignmentModel.counter_limit - 1)
    )
    if result.rowcount == 0:
        await session.delete(assignment)

    return Response(status_code=204)


@orders_control_api_router.post("/create/")
async def create_verification_entry_by_order(
    verification_entry_data_raw: str = Form(
        ..., alias="verification_entry_data"
    ),
    new_images: List[UploadFile] = File(default_factory=list),

    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    redirect_to_metrolog_info: bool = Query(...),

    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session_begin),

    employee_data: JwtData = Depends(
        check_active_access_verification
    ),
    empl_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
    ),
    order_repo: OrderRepository = Depends(
        read_order_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    verification_entry_repo: VerificationEntryRepository = Depends(
        action_verification_entry_repository
    ),
    verifier_repo: VerifierRepository = Depends(
        read_verifier_repository
    ),
    location_repo: LocationRepository = Depends(
        action_location_repository
    ),
    equipment_repo: EquipmentRepository = Depends(
        action_equipment_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    try:
        data = json.loads(verification_entry_data_raw)
        verification_entry_data = CreateVerificationEntryForm(**data)
    except Exception as e:
        raise BadRequestError(
            detail=f"Некорректный запрос. Ошибка: {e}"
        )

    validate_company_timezone(
        verification_entry_data.company_tz,
        company_tz,
        company_id
    )

    await check_verification_limit_available(
        session=session,
        company_id=company_id,
        required_slots=1
    )

    employee_cities_id = await empl_cities_repo.get_cities_id(employee_id)

    order_city_id = await order_repo.get_order_city_id(order_id)

    if employee_cities_id:
        if order_city_id and order_city_id not in employee_cities_id:
            employee_cities_id.append(order_city_id)

        if verification_entry_data.city_id and verification_entry_data.\
                city_id not in employee_cities_id:
            raise CreateVerificationCitiesBlockError

    company_params = await company_repo.get_company_params()

    if status not in admin_director:
        verif_date_block = company_params.verification_date_block
        if verif_date_block and verif_date_block >= \
                verification_entry_data.verification_date:
            raise CreateVerificationDateBlockError

    new_factory_number = verification_entry_data.factory_number
    new_verification_date = verification_entry_data.verification_date

    exists_factory = await verification_entry_repo.exists_entry_by_factory_num(
        factory_number=new_factory_number,
        verification_date=new_verification_date
    )
    if exists_factory:
        raise CreateVerificationFactoryNumBlockError

    default_verifier = await verifier_repo.default_verifier_for_create(
        employee_id=employee_id
    )
    if not default_verifier:
        raise CreateVerificationDefaultVerifierError

    await check_equip_conditions(
        default_verifier.equipments, company_id=company_id
    )

    act_number_entry = await act_number_for_create(
        company_id=company_id,
        entry_data=verification_entry_data,
        session=session
    )
    check_act_number_limit(
        act_number_entry=act_number_entry)
    act_number_entry.count -= 1

    verifier_id = default_verifier.id

    if company_params.auto_teams:
        verification_limit = company_params.daily_verifier_verif_limit
        if not verification_limit or verification_limit < 0:
            raise VerificationLimitError

        verification_date = verification_entry_data.verification_date

        verifier_id = await get_verifier_id_create(
            verification_date=verification_date,
            employee_verifier=default_verifier,
            act_number_entry=act_number_entry,
            verification_limit=verification_limit,
            company_id=company_id,
            company_tz=company_tz,
            session=session
        )

    verification_entry = VerificationEntryModel(
        company_id=company_id, employee_id=employee_id,
        act_number_id=act_number_entry.id, verifier_id=verifier_id,
        equipments=await equipment_repo.get_valid_equipments(verifier_id)
    )

    for field, value in verification_entry_data.model_dump(
            exclude={"act_number", "company_tz"}).items():
        setattr(verification_entry, field, value)

    if verification_entry.verification_result:
        verification_entry.reason_id = None

    session.add(verification_entry)

    counter_row = await session.scalar(
        select(CounterAssignmentModel)
        .where(CounterAssignmentModel.order_id == order_id)
        .with_for_update()
    )
    if counter_row:
        if counter_row.counter_limit > 1:
            counter_row.counter_limit -= 1
        else:
            await session.delete(counter_row)

    await session.flush()

    if verification_entry.location_id:
        await location_repo.increment_count(verification_entry.location_id)

    await increment_verification_count(
        session=session,
        company_id=company_id,
        delta=1
    )

    if company_params.yandex_disk_token:
        await session.refresh(
            verification_entry,
            attribute_names=["employee", "series", "act_number"]
        )

        employee = verification_entry.employee
        employee_fio = (
            f"{employee.last_name.title()} "
            f"{employee.name.title()} "
            f"{employee.patronymic.title()}"
        )

        await process_act_number_photos(
            session=session,
            act_number_id=verification_entry.act_number_id,
            company_name=company_params.name,
            employee_fio=employee_fio,
            verification_date=verification_entry.verification_date,
            act_series=verification_entry.series.name,
            act_number=verification_entry.act_number.act_number,
            token=company_params.yandex_disk_token,
            new_images=new_images or [],
            deleted_images_id=verification_entry_data.deleted_images_id or []
        )

    if company_params.auto_metrolog:
        await session.refresh(
            verification_entry,
            attribute_names=[
                "reason", "equipments"
            ]
        )

        is_correct = None
        reason_type = None

        if not verification_entry:
            raise VerificationEntryError

        if not verification_entry.verifier_id:
            raise VerificationVerifierError

        if not verification_entry.equipments:
            raise VerificationEquipmentError

        use_opt_flag = any(e.is_opt for e in verification_entry.equipments)

        if verification_entry.reason:
            if verification_entry.reason.type == ReasonType.p_2_7_3:
                is_correct = False
                reason_type = True
            else:
                is_correct = True
                reason_type = False
        else:
            is_correct = True
            reason_type = True

        metrolog_data = MetrologInfoForm()
        metrolog_data = await right_automatisation_metrolog(
            metrolog_data, water_type=verification_entry.water_type,
            latitude=company_params.latitude,
            longitude=company_params.longitude,
            default_pressure=company_params.default_pressure,
            is_correct=is_correct,
            reason_type=reason_type,
            use_opt=use_opt_flag
        )

        metrolog_info = MetrologInfoModel(
            company_id=company_id,
            verification_id=verification_entry.id
        )

        for key, value in metrolog_data.model_dump().items():
            setattr(metrolog_info, key, value)

        session.add(metrolog_info)
        await session.flush()

        await clear_verification_cache(company_id)

        return {
            "status": "ok",
            "verification_entry_id": verification_entry.id,
            "metrolog_info_id": metrolog_info.id,
            "redirect_to": "p" if redirect_to_metrolog_info else "v"
        }

    await clear_verification_cache(company_id)
    return {
        "status": "ok",
        "verification_entry_id": verification_entry.id,
        "metrolog_info_id": None,
        "redirect_to": "m" if redirect_to_metrolog_info else "v"
    }
