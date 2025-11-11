from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional, List

from models import BaseTariff


class BaseTariffRepository:
    """Репозиторий для работы с базовыми тарифами"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, tariff_id: int) -> Optional[BaseTariff]:
        """Получить базовый тариф по ID"""
        stmt = select(BaseTariff).where(BaseTariff.id == tariff_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> List[BaseTariff]:
        """Получить все базовые тарифы"""
        stmt = select(BaseTariff).order_by(BaseTariff.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_title(self, title: str) -> Optional[BaseTariff]:
        """Получить базовый тариф по названию"""
        stmt = select(BaseTariff).where(BaseTariff.title == title)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tariff: BaseTariff) -> BaseTariff:
        """Создать новый базовый тариф"""
        self.session.add(tariff)
        await self.session.flush()
        await self.session.refresh(tariff)
        return tariff

    async def update(self, tariff: BaseTariff) -> BaseTariff:
        """Обновить существующий базовый тариф"""
        await self.session.flush()
        await self.session.refresh(tariff)
        return tariff

    async def delete(self, tariff_id: int) -> bool:
        """Удалить базовый тариф по ID"""
        stmt = delete(BaseTariff).where(BaseTariff.id == tariff_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def exists_by_title(
        self, title: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Проверить, существует ли тариф с таким названием"""
        stmt = select(BaseTariff.id).where(BaseTariff.title == title)
        if exclude_id:
            stmt = stmt.where(BaseTariff.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
