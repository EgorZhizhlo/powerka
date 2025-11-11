from typing import List, Optional
from sqlalchemy import select, exists, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import CompanyActivityModel


class CompanyActivityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_activities_in_company(
        self, company_id: int
    ) -> List[CompanyActivityModel]:
        stmt = (
            select(CompanyActivityModel)
            .where(CompanyActivityModel.company_id == company_id)
            .order_by(CompanyActivityModel.name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_activity_by_id_in_company(
        self, activity_id: int, company_id: int
    ) -> Optional[CompanyActivityModel]:
        stmt = (
            select(CompanyActivityModel)
            .where(
                CompanyActivityModel.id == activity_id,
                CompanyActivityModel.company_id == company_id,
            )
            .order_by(CompanyActivityModel.name)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_activity_by_name_in_company(
        self, name: str, company_id: int
    ) -> bool:
        stmt = select(
            exists().where(
                func.lower(func.trim(CompanyActivityModel.name))
                == func.lower(func.trim(name)),
                CompanyActivityModel.company_id == company_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar()

    async def create_activity(
        self, name: str, company_id: int
    ) -> CompanyActivityModel:
        activity = CompanyActivityModel(
            name=name.strip(),
            company_id=company_id,
        )
        self._session.add(activity)
        await self._session.flush()
        await self._session.refresh(activity)
        return activity

    async def update_activity(
        self, activity: CompanyActivityModel, new_name: str
    ) -> CompanyActivityModel:
        activity.name = new_name.strip()
        await self._session.flush()
        await self._session.refresh(activity)
        return activity

    async def delete_activity(
        self, activity: CompanyActivityModel
    ) -> None:
        await self._session.delete(activity)
        await self._session.flush()
