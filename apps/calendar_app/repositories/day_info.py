from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CompanyCalendarDayInfoModel
from core.db.base_repository import BaseRepository


class DayInfoRepository(BaseRepository[CompanyCalendarDayInfoModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CompanyCalendarDayInfoModel, session)

    async def get_by_date(self, company_id: int, day: date):
        stmt = select(self.model).where(
            self.model.company_id == company_id,
            self.model.date == day
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_range(self, company_id: int, date_for: date, date_to: date):
        stmt = select(self.model).where(
            self.model.company_id == company_id,
            self.model.date.between(date_for, date_to)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
