from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session, async_db_session_begin

from core.config import settings
from apps.calendar_app.repositories import (
    CompanyRepository, CompanyCalendarRepository
)


DEFAULT_CALENDAR_PARAMS = {
    "customer_field": False,
    "customer_field_required": False,
    "price_field": False,
    "price_field_required": False,
    "water_field": False,
    "water_field_required": False,
}

FIELDS = list(DEFAULT_CALENDAR_PARAMS.keys())


class CompanyService:
    def __init__(self, session: AsyncSession):
        self.company_repo = CompanyRepository(session)
        self.calendar_repo = CompanyCalendarRepository(session)

    async def get_companies(self, employee_id: int, status: str):
        if status in settings.DIRECTOR_AUDITOR_DISPATCHERS:
            return await self.company_repo.get_for_employee(employee_id)
        return await self.company_repo.get_all()

    async def get_company_calendar_params(self, company_id: int) -> dict:
        params = await self.calendar_repo.get_by_company_id(company_id)
        if not params:
            return DEFAULT_CALENDAR_PARAMS.copy()
        return {field: getattr(params, field) for field in FIELDS}


def get_read_company_service(
        session: AsyncSession = Depends(async_db_session)
) -> CompanyService:
    return CompanyService(session)


def get_action_company_service(
        session: AsyncSession = Depends(async_db_session_begin)
) -> CompanyService:
    return CompanyService(session)
