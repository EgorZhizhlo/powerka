from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions.frontend import (
    NotFoundError,
    FrontendCreateVerifDefaultVerifierError
)

from access_control import (
    JwtData,
    check_access_verification,
    admin_director
)

from apps.verification_app.common import (
    check_equip_conditions,
)
from apps.verification_app.repositories import (
    ActSeriesRepository, read_act_series_repository,
    VerifierRepository, read_verifier_repository,
    EmployeeCitiesRepository, read_employee_cities_repository,
    CityRepository, read_city_repository,
    LocationRepository, read_location_repository,
    ReasonRepository, read_reason_repository,
    RegistryNumberRepository, read_registry_number_repository,
    CompanyRepository, read_company_repository,
    EmployeeRepository, read_employee_repository,
    OrderRepository, read_order_repository
)


orders_control_frontend_router = APIRouter(prefix='/orders-control')
templates = Jinja2Templates(directory="templates/verification")


@orders_control_frontend_router.get("/", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_access_verification),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    context = {
        "request": request,
        "company_id": company_id,
        "title_name": "Мои заявки",
        "companies": await company_repo.get_companies_for_user(
            status=status,
            employee_id=employee_id
        ),
    }
    context.update(employee_data.__dict__)

    return templates.TemplateResponse(
        "orders_control/view.html",
        context
    )


@orders_control_frontend_router.get(
    "/create/", response_class=HTMLResponse)
async def create_verification_entry_by_order_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    order_id: int = Query(..., ge=1, le=settings.max_int),
    company_tz: str = Depends(get_company_timezone),
    employee_data: JwtData = Depends(check_access_verification),
    employee_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
    ),
    order_repo: OrderRepository = Depends(
        read_order_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    verifier_repo: VerifierRepository = Depends(
        read_verifier_repository
    ),
    city_repo: CityRepository = Depends(
        read_city_repository
    ),
    act_series_repo: ActSeriesRepository = Depends(
        read_act_series_repository
    ),
    location_repo: LocationRepository = Depends(
        read_location_repository
    ),
    reason_repo: ReasonRepository = Depends(
        read_reason_repository
    ),
    registry_number_repo: RegistryNumberRepository = Depends(
        read_registry_number_repository
    ),
    employee_repo: EmployeeRepository = Depends(
        read_employee_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    if status not in admin_director:
        await order_repo.check_verification_date_block(
            order_id=order_id
        )

    default_verifier = await verifier_repo.default_verifier_for_create(
        employee_id=employee_id
    )

    if not default_verifier:
        raise FrontendCreateVerifDefaultVerifierError(
            company_id=company_id
        )

    await check_equip_conditions(
        default_verifier.equipments, for_view=True,
        company_id=company_id
    )

    c_field = await company_repo.get_company_additional_and_auto_year()

    employee_city_ids = await employee_cities_repo.get_cities_id(
        employee_id=employee_id
    )

    default_city_id, default_series_id = (
        await employee_repo.get_default_fields(
            employee_id=employee_id
        )
    )

    order = await order_repo.get_order_by_id(order_id=order_id)

    if not order:
        raise NotFoundError(
            detail="Заявка не найден или не принадлежит данной компании!",
            company_id=company_id,
        )

    prefill = {
        "verification_date": order.date.isoformat()
        if order.date
        else None,
        "city_id": order.city_id,
        "address": order.address,
        "client_full_name": order.client_full_name,
        "client_phone": order.phone_number,
        "legal_entity": order.legal_entity,
    }

    context = {
        "request": request,
        "company_id": company_id,
        "company_tz": company_tz,
        "title_name": "Добавление записи поверки по заявке",
        "companies": await company_repo.get_companies_for_user(
            employee_id=employee_id,
            status=status
        ),
        "cities": await city_repo.get_cities_for_company(
            employee_city_ids=employee_city_ids
        ),
        "locations": await location_repo.get_locations_for_company(),
        "series": await act_series_repo.get_act_series_for_company(),
        "reasons": await reason_repo.get_reasons_for_company(),
        "registry_numbers": (
            await registry_number_repo.get_registry_number_for_company()
        ),
        "default_city_id": default_city_id,
        "default_series_id": default_series_id,
        "prefill": prefill,
        "order_id": order.id,
        "image_limit_per_verification": settings.image_limit_per_verification,
    }
    context.update(employee_data.__dict__)
    context.update(c_field)

    return templates.TemplateResponse(
        "orders_control/create.html",
        context
    )
