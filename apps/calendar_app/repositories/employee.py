from sqlalchemy.ext.asyncio import AsyncSession

from core.db.base_repository import BaseRepository
from models import EmployeeModel


class EmployeeRepository(BaseRepository[EmployeeModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(EmployeeModel, session)
