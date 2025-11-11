from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists, func

from models import CompanySiTypeModel


class CompanySiTypeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_si_types_in_company(
        self, company_id: int
    ) -> List[CompanySiTypeModel]:
        stmt = (
            select(CompanySiTypeModel)
            .where(CompanySiTypeModel.company_id == company_id)
            .order_by(CompanySiTypeModel.name)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_si_type_by_id_in_company(
        self, si_type_id: int, company_id: int
    ) -> Optional[CompanySiTypeModel]:
        stmt = (
            select(CompanySiTypeModel)
            .where(
                CompanySiTypeModel.id == si_type_id,
                CompanySiTypeModel.company_id == company_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_si_type_by_name_in_company(
        self, name: str, company_id: int
    ) -> bool:
        stmt = select(
            exists().where(
                func.lower(func.trim(CompanySiTypeModel.name))
                == func.lower(func.trim(name)),
                CompanySiTypeModel.company_id == company_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar()

    async def create_si_type(
        self, name: str, company_id: int
    ) -> CompanySiTypeModel:
        si_type = CompanySiTypeModel(
            name=name.strip(),
            company_id=company_id,
        )
        self._session.add(si_type)
        await self._session.flush()
        await self._session.refresh(si_type)
        return si_type

    async def update_si_type(
        self, si_type: CompanySiTypeModel, new_name: str
    ) -> CompanySiTypeModel:
        si_type.name = new_name.strip()
        self._session.add(si_type)
        await self._session.flush()
        await self._session.refresh(si_type)
        return si_type

    async def delete_si_type(
        self, si_type: CompanySiTypeModel
    ) -> None:
        await self._session.delete(si_type)
        await self._session.flush()
