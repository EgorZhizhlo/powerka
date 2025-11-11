from typing import Optional, List, Tuple
from datetime import date as date_

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, exists, func, cast, String

from models import EquipmentModel, EquipmentInfoModel
from core.db import BaseRepository


class EquipmentRepository(BaseRepository[EquipmentModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(EquipmentModel, session)

    def _apply_deleted_filter(
            self, stmt, only_active: bool, only_deleted: bool):
        if only_deleted:
            stmt = stmt.where(EquipmentModel.is_deleted.is_(True))
        elif only_active:
            stmt = stmt.where(EquipmentModel.is_deleted.isnot(True))
        return stmt

    async def exists_with_factory_number(
        self,
        company_id: int,
        name: str,
        factory_number: str,
        exclude_id: Optional[int] = None,
    ) -> bool:
        filters = [
            func.lower(EquipmentModel.name) == func.lower(name),
            func.lower(EquipmentModel.factory_number) == func.lower(
                factory_number),
            EquipmentModel.company_id == company_id,
        ]
        if exclude_id:
            filters.append(EquipmentModel.id != exclude_id)

        stmt = select(exists().where(*filters))
        return (await self.session.execute(stmt)).scalar()

    async def exists_with_inventory_number(
        self,
        company_id: int,
        inventory_number: str,
        exclude_id: Optional[int] = None,
    ) -> bool:
        filters = [
            EquipmentModel.inventory_number == inventory_number,
            EquipmentModel.company_id == company_id,
        ]
        if exclude_id:
            filters.append(EquipmentModel.id != exclude_id)

        stmt = select(exists().where(*filters))
        return (await self.session.execute(stmt)).scalar()

    async def create(
        self, company_id: int, **fields
    ) -> EquipmentModel:
        obj = EquipmentModel(company_id=company_id)
        for field, value in fields.items():
            if value is not None:
                setattr(obj, field, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(
        self, equipment: EquipmentModel, **fields
    ) -> EquipmentModel:
        for field, value in fields.items():
            if value is not None:
                setattr(equipment, field, value)
        self.session.add(equipment)
        await self.session.flush()
        return equipment

    async def get_by_id(
        self,
        equipment_id: int,
        company_id: int,
        with_info: bool = False,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> Optional[EquipmentModel]:
        stmt = (
            select(EquipmentModel)
            .where(
                EquipmentModel.id == equipment_id,
                EquipmentModel.company_id == company_id,
            )
        )
        stmt = self._apply_deleted_filter(stmt, only_active, only_deleted)

        if with_info:
            stmt = stmt.options(selectinload(EquipmentModel.equipment_info))

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_in_company(
        self,
        company_id: int,
        with_info: bool = False,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> List[EquipmentModel]:
        stmt = (
            select(EquipmentModel)
            .where(EquipmentModel.company_id == company_id)
            .order_by(
                EquipmentModel.inventory_number.asc(),
                EquipmentModel.name
            )
        )
        stmt = self._apply_deleted_filter(stmt, only_active, only_deleted)

        if with_info:
            stmt = stmt.options(selectinload(EquipmentModel.equipment_info))

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_paginated(
        self,
        company_id: int,
        page: int,
        per_page: int,
        name: Optional[str] = None,
        factory_number: Optional[str] = None,
        inventory_number: Optional[str] = None,
        register_number: Optional[str] = None,
        verif_date_from: Optional[date_] = None,
        verif_date_to: Optional[date_] = None,
        only_active: bool = False,
        only_deleted: bool = False,
    ) -> Tuple[List[EquipmentModel], int]:
        filters = [EquipmentModel.company_id == company_id]
        stmt = select(EquipmentModel).where(*filters)

        # статус
        stmt = self._apply_deleted_filter(stmt, only_active, only_deleted)

        # текстовые фильтры
        if name:
            stmt = stmt.where(EquipmentModel.name.ilike(f"%{name}%"))
        if factory_number:
            stmt = stmt.where(
                EquipmentModel.factory_number.ilike(f"%{factory_number}%"))
        if inventory_number:
            stmt = stmt.where(cast(EquipmentModel.inventory_number, String).like(
                f"%{inventory_number}%"))
        if register_number:
            stmt = stmt.where(
                EquipmentModel.register_number.ilike(f"%{register_number}%"))

        # фильтр по дате поверки
        if verif_date_from and verif_date_to and verif_date_from > verif_date_to:
            verif_date_from, verif_date_to = verif_date_to, verif_date_from

        if verif_date_from or verif_date_to:
            date_filters = []
            if verif_date_from:
                date_filters.append(
                    EquipmentInfoModel.verif_date >= verif_date_from)
            if verif_date_to:
                date_filters.append(
                    EquipmentInfoModel.verif_date <= verif_date_to)
            stmt = stmt.where(
                exists().where(
                    EquipmentInfoModel.equipment_id == EquipmentModel.id,
                    *date_filters,
                )
            )

        # считаем total
        count_stmt = stmt.with_only_columns(func.count(EquipmentModel.id))
        total = (await self.session.execute(count_stmt)).scalar_one()

        # пагинация
        offset = (page - 1) * per_page
        stmt = stmt.order_by(
            EquipmentModel.is_deleted.isnot(True).desc(),
            EquipmentModel.inventory_number.asc(),
            EquipmentModel.name,
        ).limit(per_page).offset(offset)

        rows = (await self.session.execute(stmt)).scalars().all()
        return rows, total

    async def get_file(
        self,
        equipment_id: int,
        company_id: int,
        field: str,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> Optional[bytes]:
        column = getattr(EquipmentModel, field)
        stmt = (
            select(column)
            .where(
                EquipmentModel.id == equipment_id,
                EquipmentModel.company_id == company_id,
            )
        )
        stmt = self._apply_deleted_filter(stmt, only_active, only_deleted)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_image(
        self,
        equipment_id: int,
        company_id: int,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> Optional[bytes]:
        return await self.get_file(equipment_id, company_id, "image", only_active, only_deleted)

    async def get_image2(
        self,
        equipment_id: int,
        company_id: int,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> Optional[bytes]:
        return await self.get_file(equipment_id, company_id, "image2", only_active, only_deleted)

    async def get_document(
        self,
        equipment_id: int,
        company_id: int,
        only_active: bool = True,
        only_deleted: bool = False,
    ) -> Optional[bytes]:
        return await self.get_file(equipment_id, company_id, "document_pdf", only_active, only_deleted)
