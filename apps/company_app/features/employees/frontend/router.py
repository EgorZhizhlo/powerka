from fastapi import APIRouter, Request, Depends, Query

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company
)

from core.config import settings
from core.templates.template_manager import templates
from core.exceptions.frontend.common import (
    NotFoundError, ForbiddenError
)

from infrastructure.db import async_db_session

from models import (
    ActSeriesModel, EmployeeModel, CompanyModel, CityModel, VerifierModel,
    RouteModel
)
from models.enums import EmployeeStatus

from apps.company_app.common import make_context


employees_frontend_router = APIRouter(
    prefix="/employees"
)


@employees_frontend_router.get("/")
async def view_employees(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    context = {
        "request": request,
        "per_page": settings.entries_per_page
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "employees/view.html",
        context=context
    )


@employees_frontend_router.get("/create")
async def view_create_employees(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    verifiers = (await session.execute(
        select(VerifierModel)
        .where(
            VerifierModel.company_id == company_id
        )
    )).scalars().all()

    cities = (await session.execute(
        select(CityModel)
        .where(
            CityModel.company_id == company_id
        )
    )).scalars().all()

    series = (await session.execute(
        select(ActSeriesModel)
        .where(
            ActSeriesModel.company_id == company_id
        )
    )).scalars().all()

    routes = (
        await session.execute(
            select(RouteModel)
            .where(
                RouteModel.company_id == company_id
            )
        )
    ).scalars().all()

    context = {
        "request": request,
        "verifiers": verifiers,
        "series": series,
        "cities": cities,
        "routes": routes,
        "view_type": "create",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "employees/update_or_create.html",
        context=context
    )


@employees_frontend_router.get("/update")
async def update_employee(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session),
):
    status = user_data.status
    user_id = user_data.id

    employee = (
        await session.execute(
            select(EmployeeModel)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.companies.any(CompanyModel.id == company_id)
            )
            .options(
                selectinload(EmployeeModel.default_verifier),
                selectinload(EmployeeModel.default_city),
                selectinload(EmployeeModel.cities),
                selectinload(EmployeeModel.routes)
            )
        )
    ).scalar_one_or_none()

    if not employee:
        raise NotFoundError(
            company_id=company_id,
            detail="Сотрудник не найден!"
        )

    if status == EmployeeStatus.director:
        if user_id != employee.id:
            allowed_statuses = {
                EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
                EmployeeStatus.dispatcher2, EmployeeStatus.verifier
            }
        else:
            allowed_statuses = {
                EmployeeStatus.director, EmployeeStatus.auditor,
                EmployeeStatus.dispatcher1, EmployeeStatus.dispatcher2,
                EmployeeStatus.verifier
            }
    else:
        allowed_statuses = {
            EmployeeStatus.admin, EmployeeStatus.director,
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }

    if employee.status not in allowed_statuses:
        raise ForbiddenError(
            company_id=company_id,
            detail="В доступе к сотруднику отказано!"
        )

    verifiers = (await session.execute(
        select(VerifierModel)
        .where(
            VerifierModel.company_id == company_id
        )
        .order_by(VerifierModel.id)
    )).scalars().all()

    series = (await session.execute(
        select(ActSeriesModel)
        .where(
            ActSeriesModel.company_id == company_id
        )
        .order_by(ActSeriesModel.id)
    )).scalars().all()

    cities = (await session.execute(
        select(CityModel)
        .where(
            CityModel.company_id == company_id
        )
    )).scalars().all()

    routes = (
        await session.execute(
            select(RouteModel)
            .where(
                RouteModel.company_id == company_id
            )
        )
    ).scalars().all()

    context = {
        "request": request,
        "verifiers": verifiers,
        "series": series,
        "employee": employee,
        "cities": cities,
        "routes": routes,
        "view_type": "update",
    }
    context.update(await make_context(session, user_data, company_id))

    return templates.company.TemplateResponse(
        "employees/update_or_create.html",
        context=context
    )
