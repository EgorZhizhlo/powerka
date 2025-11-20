from types import SimpleNamespace
from fastapi import APIRouter, Request, Depends, Query

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
    check_companies_access,
)

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.timezones import ALL_TIMEZONES
from core.templates.template_manager import templates
from core.exceptions.frontend.common import (
    NotFoundError, ForbiddenError
)

from infrastructure.db import async_db_session
from infrastructure.cache import redis

from models import (
    EmployeeModel, CompanyModel,
    CompanyCalendarParameterModel
)
from models.enums import EmployeeStatus

from apps.company_app.common import _company_delete_key, make_context
from apps.tariff_app.services import tariff_cache
from apps.tariff_app.repositories import CompanyTariffStateRepository


companies_menu_frontend_router = APIRouter(prefix="")


@companies_menu_frontend_router.get("/")
async def view_companies(
    request: Request,
    user_data: JwtData = Depends(check_companies_access),
    session: AsyncSession = Depends(async_db_session),
):
    status = user_data.status
    employee_id = user_data.id

    match status:
        case EmployeeStatus.admin:
            companies = (
                await session.execute(
                    select(CompanyModel)
                    .order_by(CompanyModel.name)
                )
            ).scalars().all()
        case EmployeeStatus.director | EmployeeStatus.auditor:
            companies = (
                await session.execute(
                    select(CompanyModel)
                    .where(CompanyModel.employees.any(
                        EmployeeModel.id == employee_id))
                    .order_by(CompanyModel.name)
                )
            ).scalars().all()

    voted_company_ids: set[int] = set()
    if status == EmployeeStatus.admin:
        for c in companies:
            key = _company_delete_key(c.id)
            if await redis.sismember(key, str(employee_id)):
                voted_company_ids.add(c.id)

    context = {
        "companies": companies,
        "voted_company_ids": voted_company_ids,
        "request": request,
        **user_data.__dict__,
    }

    return templates.company.TemplateResponse(
        "companies_menu/view.html",
        context=context
    )


@companies_menu_frontend_router.get("/company")
async def view_company(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
    }
    company_employee_context = await make_context(
        session, user_data, company_id)
    context.update(company_employee_context)

    async def fetch_tariff_from_db():
        state_repo = CompanyTariffStateRepository(session)
        return await state_repo.get_by_company(company_id)

    tariff_info = await tariff_cache.get_or_fetch_limits(
        company_id, fetch_tariff_from_db
    )

    context["tariff_info"] = tariff_info

    return templates.company.TemplateResponse(
        "companies_menu/menu.html",
        context
    )


@companies_menu_frontend_router.get("/create")
async def view_create_company(
    request: Request,
    user_data: JwtData = Depends(check_companies_access),
    session: AsyncSession = Depends(async_db_session),
):
    if user_data.status != EmployeeStatus.admin:
        raise ForbiddenError(
            detail="Доступ только для администратора!"
        )

    all_employees = (await session.execute(
        select(EmployeeModel)
        .where(
            or_(
                EmployeeModel.status == EmployeeStatus.admin,
                and_(
                    EmployeeModel.status != EmployeeStatus.admin,
                    ~EmployeeModel.companies.any()
                )
            )
        )
        .order_by(
            EmployeeModel.last_name,
            EmployeeModel.name,
            EmployeeModel.patronymic)
    )).scalars().all()

    company = None
    company_calendar_params = SimpleNamespace(
        customer_field=False, customer_field_required=False,
        price_field=False, price_field_required=False,
        water_field=False, water_field_required=False,
    )

    context = {
        "request": request,
        "view_type": "create",
        "company": company,
        "company_calendar_params": company_calendar_params,
        "all_employees": all_employees,
        "selected_employee_ids": [],
        "timezones": ALL_TIMEZONES,
        **user_data.__dict__,
    }
    return templates.company.TemplateResponse(
        "companies_menu/update_or_create.html", context=context
    )


@companies_menu_frontend_router.get("/update")
async def view_update_company(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    company = (
        await session.execute(
            select(CompanyModel)
            .where(CompanyModel.id == company_id)
            .options(
                selectinload(CompanyModel.activities),
                selectinload(CompanyModel.si_types),
                selectinload(CompanyModel.employees)
            )
        )
    ).scalar_one_or_none()

    company_calendar_params = (await session.execute(
        select(CompanyCalendarParameterModel)
        .where(CompanyCalendarParameterModel.company_id == company_id)
    )).scalar_one_or_none()

    if not company_calendar_params:
        raise NotFoundError(
            company_id=company_id,
            detail="Дополнительные параметры для календаря не найдены!"
        )

    all_employees = []
    selected_employee_ids = []
    if user_data.status == EmployeeStatus.admin:
        all_employees = (await session.execute(
            select(EmployeeModel)
            .where(
                or_(
                    EmployeeModel.companies.any(CompanyModel.id == company_id),
                    EmployeeModel.status == EmployeeStatus.admin,
                    and_(
                        EmployeeModel.status != EmployeeStatus.admin,
                        ~EmployeeModel.companies.any()
                    )
                )
            )
            .order_by(
                EmployeeModel.last_name,
                EmployeeModel.name,
                EmployeeModel.patronymic)
        )).scalars().all()
        selected_employee_ids = [e.id for e in (company.employees or [])]

    context = {
        "request": request,
        "view_type": "update",
        "company": company,
        "company_calendar_params": company_calendar_params,
        "all_employees": all_employees,
        "selected_employee_ids": selected_employee_ids,
        "timezones": ALL_TIMEZONES,
        **user_data.__dict__,
    }

    return templates.company.TemplateResponse(
        "companies_menu/update_or_create.html",
        context=context
    )
