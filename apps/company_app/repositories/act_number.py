import math
from typing import List, Optional, Tuple

from sqlalchemy import select, exists, func, cast, String
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActNumberModel, CityModel, ActSeriesModel
from core.db.base_repository import BaseRepository


class ActNumberRepository(BaseRepository[ActNumberModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(ActNumberModel, session)

    async def get_all_by_company(
        self, company_id: int
    ) -> List[ActNumberModel]:
        stmt = (
            select(ActNumberModel)
            .where(
                ActNumberModel.company_id == company_id,
                ActNumberModel.is_deleted.isnot(True),
            )
            .order_by(ActNumberModel.act_number)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_paginated(
        self,
        company_id: int,
        page: int = 1,
        per_page: int = 20,
        search: str = ""
    ) -> Tuple[List[ActNumberModel], int, int]:
        search_clause = (
            cast(ActNumberModel.act_number, String).ilike(f"%{search}%")
            | ActNumberModel.client_full_name.ilike(f"%{search}%")
            | ActNumberModel.client_phone.ilike(f"%{search}%")
            | ActNumberModel.address.ilike(f"%{search}%")
        )

        total = (
            await self.session.execute(
                select(func.count(ActNumberModel.id)).where(
                    ActNumberModel.company_id == company_id,
                    search_clause,
                )
            )
        ).scalar_one()

        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        stmt = (
            select(ActNumberModel)
            .where(
                ActNumberModel.company_id == company_id,
                search_clause,
            )
            .order_by(
                ActNumberModel.is_deleted.isnot(True).desc(),
                ActNumberModel.act_number,
            )
            .options(
                selectinload(
                    ActNumberModel.city
                ).load_only(CityModel.name),
                selectinload(
                    ActNumberModel.series
                ).load_only(ActSeriesModel.name),
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
        self, act_number_id: int, company_id: int
    ) -> Optional[ActNumberModel]:
        stmt = select(ActNumberModel).where(
            ActNumberModel.id == act_number_id,
            ActNumberModel.company_id == company_id,
            ActNumberModel.is_deleted.isnot(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_duplicate(
        self,
        act_number: str,
        series_id: int,
        company_id: int,
        exclude_id: Optional[int] = None,
    ) -> bool:
        conditions = [
            ActNumberModel.act_number == act_number,
            ActNumberModel.series_id == series_id,
            ActNumberModel.company_id == company_id,
        ]
        if exclude_id:
            conditions.append(ActNumberModel.id != exclude_id)

        stmt = select(exists().where(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar()

    async def create(
        self, company_id: int, **fields
    ) -> ActNumberModel:
        obj = ActNumberModel(company_id=company_id)
        for field, value in fields.items():
            if value is not None:
                setattr(obj, field, value)

        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(
        self, act_number_obj: ActNumberModel, **fields
    ) -> ActNumberModel:
        for field, value in fields.items():
            if value is not None:
                setattr(act_number_obj, field, value)

        self.session.add(act_number_obj)
        await self.session.flush()
        await self.session.refresh(act_number_obj)
        return act_number_obj

    async def delete_or_soft_delete(
        self, act_number: ActNumberModel
    ) -> None:
        if not act_number.verification:
            await self.session.delete(act_number)
        else:
            act_number.is_deleted = True

        await self.session.flush()

    async def restore(
        self, act_number_id: int, company_id: int
    ) -> Optional[ActNumberModel]:
        stmt = (
            select(ActNumberModel)
            .where(
                ActNumberModel.id == act_number_id,
                ActNumberModel.company_id == company_id,
                ActNumberModel.is_deleted.is_(True),
            )
            .options(
                joinedload(
                    ActNumberModel.series
                ).load_only(ActSeriesModel.is_deleted),
                joinedload(
                    ActNumberModel.city
                ).load_only(CityModel.is_deleted),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
