from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import Query, Depends
from typing import Optional
from datetime import date

from core.config import settings

from infrastructure.db import async_db_session

from models import CalendarReportModel, OrderModel
from models.enums import EmployeeStatus


class CalendarReportRepository:
    def __init__(self, session: AsyncSession, company_id: int):
        self.session = session
        self.company_id = company_id

    async def get_report_config(
        self, report_id: int
    ) -> CalendarReportModel | None:
        query = (
            select(CalendarReportModel)
            .where(
                CalendarReportModel.id == report_id,
                CalendarReportModel.company_id == self.company_id
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_dynamic_report_entries(
        self,
        report_config: CalendarReportModel,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        employee_id: Optional[int] = None,
    ) -> list[OrderModel]:

        base_conditions = [
            OrderModel.company_id == self.company_id,
            OrderModel.is_active.is_(True)
        ]

        if employee_id:
            base_conditions.append(OrderModel.dispatcher_id == employee_id)

        if not report_config.no_date:
            base_conditions.append(OrderModel.no_date == False)
            if start_date:
                base_conditions.append(OrderModel.date >= start_date)
            if end_date:
                base_conditions.append(OrderModel.date <= end_date)
        else:
            if start_date or end_date:
                with_date_conditions = [
                    OrderModel.no_date == False
                ]
                if start_date:
                    with_date_conditions.append(OrderModel.date >= start_date)
                if end_date:
                    with_date_conditions.append(OrderModel.date <= end_date)

                without_date_conditions = [
                    OrderModel.no_date == True
                ]
                if start_date:
                    without_date_conditions.append(
                        OrderModel.date_of_get >= start_date
                    )
                if end_date:
                    without_date_conditions.append(
                        OrderModel.date_of_get <= end_date
                    )

                base_conditions.append(
                    or_(
                        and_(*with_date_conditions),
                        and_(*without_date_conditions)
                    )
                )

        query = select(OrderModel).where(and_(*base_conditions)).options(
            selectinload(OrderModel.dispatcher),
            selectinload(OrderModel.route)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_all_reports(self) -> list[CalendarReportModel]:
        query = (
            select(
                CalendarReportModel
            )
            .where(
                CalendarReportModel.company_id == self.company_id
            )
            .order_by(CalendarReportModel.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_reports_by_status(
        self, status: EmployeeStatus
    ) -> list[CalendarReportModel]:
        query = select(CalendarReportModel).where(
            CalendarReportModel.company_id == self.company_id
        )

        if status in settings.AUDITOR_DISPATCHERS:
            if status == EmployeeStatus.auditor:
                query = query.where(
                    CalendarReportModel.for_auditor.is_(True)
                )
            elif status == EmployeeStatus.dispatcher1:
                query = query.where(
                    CalendarReportModel.for_dispatcher1.is_(True)
                )
            elif status == EmployeeStatus.dispatcher2:
                query = query.where(
                    CalendarReportModel.for_dispatcher2.is_(True)
                )

        query = query.order_by(CalendarReportModel.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())


async def read_calendar_report_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
) -> CalendarReportRepository:
    return CalendarReportRepository(session=session, company_id=company_id)
