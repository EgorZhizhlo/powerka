from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.db.base_repository import BaseRepository
from models import CompanyModel, EmployeeModel


class CompanyRepository(BaseRepository[CompanyModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CompanyModel, session)

    async def get_all(self):
        q = select(
            CompanyModel.id, CompanyModel.name
        ).order_by(
            CompanyModel.name
        )
        result = await self.session.execute(q)
        return result.mappings().all()

    async def get_for_employee(self, employee_id: int):
        q = (
            select(
                CompanyModel.id, CompanyModel.name
            )
            .where(
                CompanyModel.employees.any(
                    EmployeeModel.id == employee_id
                )
            )
            .order_by(CompanyModel.name)
        )
        result = await self.session.execute(q)
        return result.mappings().all()
