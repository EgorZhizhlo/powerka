from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update, func
from typing import Optional, List
from datetime import date

from models import CompanyTariffHistory


class CompanyTariffHistoryRepository:
    """Репозиторий для работы с историей тарифов компании"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self, history_id: int, *, for_update: bool = False
    ) -> Optional[CompanyTariffHistory]:
        """Получить запись истории по ID"""
        stmt = select(CompanyTariffHistory).where(
            CompanyTariffHistory.id == history_id
        )

        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_company(
        self, company_id: int, *, for_update: bool = False
    ) -> Optional[CompanyTariffHistory]:
        """Получить активный тариф компании"""
        stmt = (
            select(CompanyTariffHistory)
            .where(
                CompanyTariffHistory.company_id == company_id,
                CompanyTariffHistory.is_active.is_(True)
            )
            .order_by(desc(CompanyTariffHistory.created_at))
            .limit(1)
        )

        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history_by_company(
        self,
        company_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[CompanyTariffHistory]:
        """Получить историю тарифов компании с пагинацией"""
        stmt = (
            select(CompanyTariffHistory)
            .where(CompanyTariffHistory.company_id == company_id)
            .order_by(desc(CompanyTariffHistory.created_at))
        )

        if limit:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_history_by_company(self, company_id: int) -> int:
        """Подсчитать общее количество записей истории для компании"""
        stmt = (
            select(func.count())
            .select_from(CompanyTariffHistory)
            .where(CompanyTariffHistory.company_id == company_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def create(
        self, history: CompanyTariffHistory
    ) -> CompanyTariffHistory:
        """Создать запись в истории"""
        self.session.add(history)
        await self.session.flush()
        await self.session.refresh(history)
        return history

    async def deactivate_previous(
        self, company_id: int, reason: str = "Назначен новый тариф"
    ) -> int:
        """Деактивировать все предыдущие тарифы компании"""
        stmt = (
            update(CompanyTariffHistory)
            .where(
                CompanyTariffHistory.company_id == company_id,
                CompanyTariffHistory.is_active.is_(True)
            )
            .values(is_active=False, reason=reason)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def close_previous_tariff(
        self, company_id: int, end_date: date
    ) -> int:
        """Закрыть предыдущий активный тариф установкой valid_to"""
        stmt = (
            update(CompanyTariffHistory)
            .where(
                CompanyTariffHistory.company_id == company_id,
                CompanyTariffHistory.is_active.is_(True),
                CompanyTariffHistory.valid_to.is_(None)
            )
            .values(valid_to=end_date)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
