from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.db.base_repository import BaseRepository
from models import CompanyCalendarParameterModel


class CompanyCalendarRepository(BaseRepository[CompanyCalendarParameterModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CompanyCalendarParameterModel, session)

    async def get_by_company_id(self, company_id: int):
        q = select(CompanyCalendarParameterModel).where(
            CompanyCalendarParameterModel.company_id == company_id
        )
        return await self.session.scalar(q)
