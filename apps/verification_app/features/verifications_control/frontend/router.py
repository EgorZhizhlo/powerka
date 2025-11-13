from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.db import async_db_session

from models import (
    ActSeriesModel, EmployeeModel, CompanyModel, CityModel, VerifierModel,
    VerificationEntryModel, ActNumberModel,
    VerificationReportModel, VerificationEntryPhotoModel
)

from access_control import (
    JwtData,
    check_access_verification,
    check_active_access_verification,
    access_verification,
    admin_director,
    verifier
)

from core.config import settings, format_date
from core.db.dependencies import get_company_timezone
from core.exceptions import (
    check_is_none,
    CustomCreateVerifDefaultVerifierException
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
)


verifications_control_frontend_router = APIRouter(prefix='')
templates = Jinja2Templates(
    directory="templates/verification")
templates.env.filters['strftime'] = format_date


async def get_any_from_models(
    session: AsyncSession,
    model,
    company_id: int,
):
    stmt = (
        select(model)
        .where(
            model.company_id == company_id,
        )
        .order_by(model.name)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@verifications_control_frontend_router.get("/", response_class=HTMLResponse)
async def verifications_entry_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
    employee_data: JwtData = Depends(check_access_verification),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    )
):
    employees = None
    if employee_data.status in admin_director:
        employees = (
            await session.execute(
                select(
                    EmployeeModel.id, EmployeeModel.last_name,
                    EmployeeModel.name, EmployeeModel.patronymic
                ).where(
                    EmployeeModel.companies.any(CompanyModel.id == company_id),
                    EmployeeModel.status.in_(access_verification)
                )
                .order_by(
                    EmployeeModel.last_name, EmployeeModel.name,
                    EmployeeModel.patronymic
                )
            )
        ).mappings().all()

    context = {
        "request": request,
        "company_id": company_id,
        "title_name": "Таблица записей поверки",
        "companies": await company_repo.get_companies_for_user(
            status=employee_data.status,
            employee_id=employee_data.id
        ),
        "employees": employees,
        "series": await get_any_from_models(
            session=session,
            model=ActSeriesModel,
            company_id=company_id,
        ),
        "cities": await get_any_from_models(
            session=session,
            model=CityModel,
            company_id=company_id,
        ),
        "reports": await get_any_from_models(
            session=session,
            model=VerificationReportModel,
            company_id=company_id,
        ),
    }
    context.update(employee_data.__dict__)

    return templates.TemplateResponse(
        "verifications_control/view.html", context)


@verifications_control_frontend_router.get(
    "/create", response_class=HTMLResponse)
async def create_verification_entry_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    company_tz: str = Depends(get_company_timezone),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    employee_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
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
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    employee_repo: EmployeeRepository = Depends(
        read_employee_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    default_verifier = await verifier_repo.default_verifier_for_create(
        employee_id=employee_id)

    if not default_verifier:
        raise CustomCreateVerifDefaultVerifierException(
            company_id=company_id)

    await check_equip_conditions(
        default_verifier.equipments, for_view=True,
        company_id=company_id)

    employee_city_ids = await employee_cities_repo.get_cities_id(
        employee_id=employee_id)

    c_field = await company_repo.get_company_additional_and_auto_year()

    default_city_id, default_series_id = (
        await employee_repo.get_default_fields(
            employee_id=employee_id
        )
    )

    context = {
        "request": request,
        "company_id": company_id,
        "company_tz": company_tz,
        "title_name": "Добавление записи поверки",
        "registry_numbers": (
            await registry_number_repo.get_registry_number_for_company()
        ),
        "companies": await company_repo.get_companies_for_user(
            employee_id=employee_id, status=status
        ),
        "cities": await city_repo.get_cities_for_company(
            employee_city_ids=employee_city_ids
        ),
        "locations": await location_repo.get_locations_for_company(),
        "series": await act_series_repo.get_act_series_for_company(),
        "reasons": await reason_repo.get_reasons_for_company(),
        "image_limit_per_verification": settings.image_limit_per_verification,
        "default_city_id": default_city_id,
        "default_series_id": default_series_id,
    }
    context.update(employee_data.__dict__)
    context.update(c_field)

    return templates.TemplateResponse(
        "verifications_control/create.html",
        context
    )


@verifications_control_frontend_router.get(
    "/update",
    response_class=HTMLResponse
)
async def update_verification_entry_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    employee_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
    ),
    city_repo: CityRepository = Depends(
        read_city_repository
    ),
    location_repo: LocationRepository = Depends(
        read_location_repository
    ),
    act_series_repo: ActSeriesRepository = Depends(
        read_act_series_repository
    ),
    reason_repo: ReasonRepository = Depends(
        read_reason_repository
    ),
    registry_number_repo: RegistryNumberRepository = Depends(
        read_registry_number_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
):
    status = employee_data.status
    employee_id = employee_data.id

    verification_entry_query = (
        select(VerificationEntryModel)
        .where(
            VerificationEntryModel.id == verification_entry_id,
            VerificationEntryModel.company_id == company_id
        )
        .options(
            selectinload(VerificationEntryModel.employee)
            .load_only(
                EmployeeModel.last_name,
                EmployeeModel.name,
                EmployeeModel.patronymic,
            ),
            selectinload(VerificationEntryModel.act_number)
            .load_only(
                ActNumberModel.act_number,
            ),
        )
    )

    if status in verifier:
        verification_entry_query = (
            verification_entry_query
            .where(VerificationEntryModel.employee_id == employee_id)
        )

    verification_entry = (
        await session.execute(verification_entry_query)).scalar_one_or_none()

    await check_is_none(
        verification_entry, type="Поверка",
        id=verification_entry_id, company_id=company_id)

    employee_city_ids = await employee_cities_repo.get_cities_id(
        employee_id=employee_id
    )

    c_field = await company_repo.get_company_additional_and_auto_year()

    verification_entry_photos = (
        await session.execute(
            select(VerificationEntryPhotoModel)
            .where(
                VerificationEntryPhotoModel.verification_entry_id == verification_entry_id)
            .order_by(VerificationEntryPhotoModel.file_name)
        )
    ).scalars().all()

    verifiers = None

    if status in admin_director:
        verifiers = (
            await session.execute(
                select(VerifierModel)
                .where(
                    VerifierModel.company_id == company_id
                )
            )
        ).scalars().all()

    context = {
        "request": request,
        "company_id": company_id,
        "company_tz": company_tz,
        "companies": await company_repo.get_companies_for_user(
            employee_id=employee_id,
            status=status
        ),
        "verifiers": verifiers,
        "image_limit_per_verification": settings.image_limit_per_verification,
        "verification_entry": verification_entry,
        "verification_entry_photos": verification_entry_photos,
        "title_name": "Редактирование записи поверки",
        "cities": await city_repo.get_cities_for_company(
            employee_city_ids=employee_city_ids
        ),
        "locations": await location_repo.get_locations_for_company(),
        "series": await act_series_repo.get_act_series_for_company(),
        "reasons": await reason_repo.get_reasons_for_company(),
        "registry_numbers": (
            await registry_number_repo.get_registry_number_for_company()
        ),
    }
    context.update(employee_data.__dict__)
    context.update(c_field)

    return templates.TemplateResponse(
        "verifications_control/update.html",
        context
    )
