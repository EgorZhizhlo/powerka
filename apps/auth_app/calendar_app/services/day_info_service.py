from datetime import date
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session, async_db_session_begin
from apps.calendar_app.repositories import DayInfoRepository


class DayInfoService:
    def __init__(self, session: AsyncSession):
        self.repo = DayInfoRepository(session)

    async def get_day_info(self, company_id: int, date_info: date):
        rec = await self.repo.get_by_date(company_id, date_info)
        return {str(date_info): rec.day_info if rec else ""}

    async def upsert_day_info(
            self, company_id: int, date_info: date, day_info: str):
        rec = await self.repo.get_by_date(company_id, date_info)

        if rec:
            rec.day_info = day_info
            await self.repo.commit()
        else:
            rec = await self.repo.add(
                self.repo.model(
                    company_id=company_id, date=date_info, day_info=day_info)
            )
            await self.repo.commit()

        return {"day_info": rec.day_info}

    async def get_calendar_day_info(
            self, company_id: int, date_for: date, date_to: date):
        recs = await self.repo.get_range(company_id, date_for, date_to)
        return {str(d.date): d.day_info for d in recs}


def get_read_day_info_service(
        session: AsyncSession = Depends(async_db_session)
) -> DayInfoService:
    return DayInfoService(session)


def get_action_day_info_service(
        session: AsyncSession = Depends(async_db_session_begin)
) -> DayInfoService:
    return DayInfoService(session)
