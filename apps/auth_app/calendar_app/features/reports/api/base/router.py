from typing import List
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    dispatchers_exception
)

from infrastructure.db import async_db_session
from models import (
    EmployeeModel, RouteModel, CompanyModel
)
from models.associations import (
    employees_companies, employees_routes
)
from core.config import settings
from apps.calendar_app.schemas.base_reports import RouteSchema, EmployeeSchema


reports_api_router = APIRouter(
    prefix="/api/reports"
)


@reports_api_router.get(
    "/dispatchers",
    response_model=List[EmployeeSchema],
    dependencies=[Depends(dispatchers_exception)]
)
async def api_report_dispatchers_list(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
):
    stmt = (
        select(
            EmployeeModel.id, EmployeeModel.last_name, EmployeeModel.name,
            EmployeeModel.patronymic, EmployeeModel.username)
        .where(
            EmployeeModel.status.in_(settings.ACCESS_CALENDAR),
            EmployeeModel.companies.any(CompanyModel.id == company_id)
        )
        .order_by(
            EmployeeModel.last_name,
            EmployeeModel.name,
            EmployeeModel.patronymic
        )
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        EmployeeSchema.model_validate(r._mapping)
        for r in rows
    ]


@reports_api_router.get(
    "/verifiers",
    response_model=list[EmployeeSchema],
    dependencies=[Depends(dispatchers_exception)]
)
async def api_report_verifers_list(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
):
    stmt = (
        select(EmployeeModel)
        .where(
            EmployeeModel.companies.any(
                employees_companies.c.company_id == company_id),
            EmployeeModel.is_active.is_(True),
            EmployeeModel.default_verifier_id.isnot(None)
        )
        .order_by(
            EmployeeModel.last_name,
            EmployeeModel.name,
            EmployeeModel.patronymic
        )
    )
    emps = (await session.execute(stmt)).scalars().all()
    return emps


@reports_api_router.get(
    "/routes",
    response_model=List[RouteSchema],
)
async def api_report_route_list(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data=Depends(dispatchers_exception),
    session: AsyncSession = Depends(async_db_session),
):
    employee_route_ids = (
        await session.execute(
            select(employees_routes.c.route_id)
            .where(employees_routes.c.employee_id == employee_data.id)
        )
    ).scalars().all()

    stmt = (
        select(RouteModel.id, RouteModel.name)
        .where(RouteModel.company_id == company_id)
        .order_by(RouteModel.name)
    )

    if employee_route_ids:
        stmt = stmt.where(RouteModel.id.in_(employee_route_ids))

    result = await session.execute(stmt)
    rows = result.all()

    return [
        RouteSchema.model_validate(r._mapping)
        for r in rows
    ]
