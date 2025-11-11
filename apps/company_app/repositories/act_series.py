import math
from typing import List, Optional, Tuple
from sqlalchemy import select, func, delete as sqla_delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActSeriesModel, ActNumberModel, CityModel
from core.db.base_repository import BaseRepository


class ActSeriesRepository(BaseRepository[ActSeriesModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(ActSeriesModel, session)

    async def get_all_by_company(
            self, company_id: int) -> List[ActSeriesModel]:
        stmt = (
            select(ActSeriesModel)
            .where(
                ActSeriesModel.company_id == company_id,
                ActSeriesModel.is_deleted.isnot(True)
            ).order_by(ActSeriesModel.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_paginated(
        self,
        company_id: int,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
    ) -> Tuple[List[ActSeriesModel], int, int]:
        search_clause = ActSeriesModel.name.ilike(f"%{search}%")

        total = (
            await self.session.execute(
                select(func.count(ActSeriesModel.id)).where(
                    ActSeriesModel.company_id == company_id,
                    search_clause,
                )
            )
        ).scalar_one()

        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        stmt = (
            select(ActSeriesModel)
            .where(ActSeriesModel.company_id == company_id, search_clause)
            .order_by(
                ActSeriesModel.is_deleted.isnot(True).desc(),
                ActSeriesModel.name,
            )
            .limit(per_page)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        objs = result.scalars().all()
        for obj in objs:
            obj.is_deleted = bool(obj.is_deleted)

        return objs, page, total_pages

    async def get_by_id(
        self, series_id: int, company_id: int
    ) -> Optional[ActSeriesModel]:
        stmt = select(ActSeriesModel).where(
            ActSeriesModel.id == series_id,
            ActSeriesModel.company_id == company_id,
            ActSeriesModel.is_deleted.isnot(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_full_for_delete(
        self, series_id: int, company_id: int
    ) -> Optional[ActSeriesModel]:
        stmt = (
            select(ActSeriesModel)
            .options(
                selectinload(ActSeriesModel.verifications),
                selectinload(ActSeriesModel.act_number)
                .selectinload(ActNumberModel.verification),
                selectinload(ActSeriesModel.employee),
            )
            .where(
                ActSeriesModel.id == series_id,
                ActSeriesModel.company_id == company_id,
                ActSeriesModel.is_deleted.isnot(True),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, company_id: int, name: str
    ) -> ActSeriesModel:
        obj = ActSeriesModel(company_id=company_id, name=name.strip())
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(
        self, series: ActSeriesModel, name: str
    ) -> ActSeriesModel:
        _name = name.strip()
        if name and _name:
            series.name = _name

        await self.session.flush()
        return series

    async def delete_or_soft_delete(self, series: ActSeriesModel) -> None:
        has_series_verif = bool(series.verifications)
        any_number_verif = any(
            bool(num.verification) for num in series.act_number)

        # обнуляем series у сотрудников
        for emp in series.employee:
            emp.series = None

        if not has_series_verif and not any_number_verif:
            await self.session.execute(
                sqla_delete(ActNumberModel).where(
                    ActNumberModel.series_id == series.id
                )
            )
            await self.session.delete(series)
        else:
            for num in series.act_number:
                num.is_deleted = True
            series.is_deleted = True
        await self.session.flush()

    async def restore(
        self, series_id: int, company_id: int
    ) -> Optional[ActSeriesModel]:
        stmt = (
            select(ActSeriesModel)
            .where(
                ActSeriesModel.id == series_id,
                ActSeriesModel.company_id == company_id,
                ActSeriesModel.is_deleted.is_(True),
            )
            .options(
                selectinload(ActSeriesModel.act_number)
                .selectinload(ActNumberModel.city)
                .load_only(CityModel.is_deleted)
            )
        )
        result = await self.session.execute(stmt)
        series = result.scalar_one_or_none()
        if not series:
            return None

        series.is_deleted = False
        for num in series.act_number:
            if not (num.city and num.city.is_deleted):
                num.is_deleted = False
        await self.session.flush()
        return series
