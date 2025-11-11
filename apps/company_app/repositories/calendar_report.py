import math
from typing import List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.base_repository import BaseRepository
from models import CalendarReportModel


class CalendarReportRepository(BaseRepository[CalendarReportModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CalendarReportModel, session)

    async def get_paginated(
        self,
        company_id: int,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
    ) -> Tuple[List[CalendarReportModel], int, int]:
        filters = [CalendarReportModel.company_id == company_id]
        if search:
            filters.append(CalendarReportModel.name.ilike(f"%{search}%"))

        total = (
            await self.session.execute(
                select(func.count(CalendarReportModel.id)).where(*filters)
            )
        ).scalar_one()

        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        stmt = (
            select(CalendarReportModel)
            .where(*filters)
            .order_by(CalendarReportModel.name)
            .limit(per_page)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        objs = result.scalars().all()
        return objs, page, total_pages

    async def get_by_id(
        self, report_id: int, company_id: int
    ) -> Optional[CalendarReportModel]:
        stmt = select(CalendarReportModel).where(
            CalendarReportModel.id == report_id,
            CalendarReportModel.company_id == company_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, company_id: int, **fields
    ) -> CalendarReportModel:
        obj = CalendarReportModel(company_id=company_id)
        for field, value in fields.items():
            if value is not None:
                setattr(obj, field, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(
        self, report: CalendarReportModel, **fields
    ) -> CalendarReportModel:
        for field, value in fields.items():
            if value is not None:
                setattr(report, field, value)
        self.session.add(report)
        await self.session.flush()
        return report

    async def delete(self, report: CalendarReportModel) -> None:
        await self.session.delete(report)
        await self.session.flush()
