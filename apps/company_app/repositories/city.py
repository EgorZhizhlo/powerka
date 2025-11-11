import math
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from models import CityModel, ActNumberModel, ActSeriesModel
from core.db import BaseRepository


class CityRepository(BaseRepository[CityModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CityModel, session)

    async def get_all_by_company(self, company_id: int) -> List[CityModel]:
        stmt = (
            select(CityModel)
            .where(
                CityModel.company_id == company_id,
                CityModel.is_deleted.isnot(True)
            ).order_by(CityModel.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_paginated(
        self,
        company_id: int,
        page: int,
        per_page: int,
        search: str = "",
    ) -> Tuple[List[CityModel], int, int]:
        filters = [CityModel.company_id == company_id]
        if search:
            filters.append(CityModel.name.ilike(f"%{search}%"))

        total = (
            await self.session.execute(
                select(func.count(CityModel.id)).where(*filters)
            )
        ).scalar_one()
        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        stmt = (
            select(CityModel)
            .where(*filters)
            .order_by(
                CityModel.is_deleted.isnot(True).desc(),
                CityModel.name
            )
            .limit(per_page)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        objs = result.scalars().all()
        for c in objs:
            c.is_deleted = bool(c.is_deleted)
        return objs, page, total_pages

    async def exists_duplicate(
        self, name: str, company_id: int, exclude_id: Optional[int] = None
    ) -> bool:
        stmt = select(func.count()).where(
            func.lower(CityModel.name) == func.lower(name),
            CityModel.company_id == company_id,
        )
        if exclude_id:
            stmt = stmt.where(CityModel.id != exclude_id)

        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def create(
        self, company_id: int, name: str
    ) -> CityModel:
        obj = CityModel(company_id=company_id, name=name.strip())
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(
        self, city: CityModel, name: str
    ) -> CityModel:
        _name = name.strip()
        if name and _name:
            city.name = _name

        await self.session.flush()
        return city

    async def get_by_id(
        self, city_id: int, company_id: int
    ) -> Optional[CityModel]:
        stmt = select(CityModel).where(
            CityModel.id == city_id,
            CityModel.company_id == company_id,
            CityModel.is_deleted.isnot(True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_full_for_delete(
        self, city_id: int, company_id: int
    ) -> Optional[CityModel]:
        stmt = (
            select(CityModel)
            .where(
                CityModel.id == city_id,
                CityModel.company_id == company_id,
                CityModel.is_deleted.isnot(True),
            )
            .options(
                selectinload(CityModel.verifications),
                selectinload(CityModel.act_numbers)
                .selectinload(ActNumberModel.verification),
                selectinload(CityModel.employee),
                selectinload(CityModel.employees),
                selectinload(CityModel.order),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, city: CityModel) -> None:
        has_city_verifs = bool(city.verifications)
        has_act_verifs = any(act.verification for act in city.act_numbers)
        has_calendar_jobs = bool(city.order)

        can_hard_delete = not (
            has_city_verifs or has_act_verifs or has_calendar_jobs)

        if city.employee:
            city.employee.default_city = None
        city.employees.clear()

        if can_hard_delete:
            for act in list(city.act_numbers):
                await self.session.delete(act)
            await self.session.flush()
            await self.session.delete(city)
        else:
            for num in city.act_numbers:
                num.is_deleted = True
            city.is_deleted = True

    async def get_full_for_restore(
        self, city_id: int, company_id: int
    ) -> Optional[CityModel]:
        stmt = (
            select(CityModel)
            .where(
                CityModel.id == city_id,
                CityModel.company_id == company_id,
                CityModel.is_deleted.is_(True),
            )
            .options(
                selectinload(CityModel.act_numbers)
                .selectinload(ActNumberModel.series)
                .load_only(ActSeriesModel.is_deleted)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def restore(self, city: CityModel) -> None:
        city.is_deleted = False
        for act in city.act_numbers:
            if not (act.series and act.series.is_deleted):
                act.is_deleted = False
