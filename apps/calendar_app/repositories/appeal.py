from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc
from sqlalchemy.orm import selectinload

from core.db.base_repository import BaseRepository
from models import AppealModel


class AppealRepository(BaseRepository[AppealModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(AppealModel, session)

    async def count_by_company(
            self, company_id: int, status: str | None = None) -> int:
        filters = [AppealModel.company_id == company_id]
        if status:
            filters.append(AppealModel.status == status)
        q = select(func.count()).where(*filters)
        result = await self.session.execute(q)
        return result.scalar_one()

    async def get_list(
        self,
        company_id: int,
        status: str | None = None,
        offset: int = 0,
        limit: int = 30,
    ):
        filters = [AppealModel.company_id == company_id]
        if status:
            filters.append(AppealModel.status == status)

        q = (
            select(AppealModel)
            .where(*filters)
            .order_by(asc(AppealModel.date_of_get))
            .options(selectinload(AppealModel.dispatcher))
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(q)
        return result.scalars().all()

    async def get_by_id_and_company(self, appeal_id: int, company_id: int):
        q = (
            select(AppealModel)
            .where(
                AppealModel.id == appeal_id,
                AppealModel.company_id == company_id,
            )
            .options(selectinload(AppealModel.dispatcher))
        )
        result = await self.session.execute(q)
        return result.scalar_one_or_none()
