from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert
from typing import Optional

from models import CompanyTariffState


class CompanyTariffStateRepository:
    """Репозиторий для работы с текущим состоянием тарифа компании"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_company(
        self, company_id: int, *, for_update: bool = False
    ) -> Optional[CompanyTariffState]:
        """Получить текущее состояние тарифа компании"""
        stmt = select(CompanyTariffState).where(
            CompanyTariffState.company_id == company_id
        )

        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, state: CompanyTariffState
    ) -> CompanyTariffState:
        """Создать состояние тарифа"""
        self.session.add(state)
        await self.session.flush()
        await self.session.refresh(state)
        return state

    async def upsert(
        self, state: CompanyTariffState
    ) -> CompanyTariffState:
        """Создать или обновить состояние тарифа (атомарная операция)"""
        stmt = insert(CompanyTariffState).values(
            company_id=state.company_id,
            valid_from=state.valid_from,
            valid_to=state.valid_to,
            max_employees=state.max_employees,
            max_verifications=state.max_verifications,
            max_orders=state.max_orders,
            used_employees=state.used_employees or 0,
            used_verifications=state.used_verifications or 0,
            used_orders=state.used_orders or 0,
            carry_over_verifications=state.carry_over_verifications,
            carry_over_orders=state.carry_over_orders,
            auto_manufacture_year=state.auto_manufacture_year,
            auto_teams=state.auto_teams,
            auto_metrolog=state.auto_metrolog,
            base_tariff_id=state.base_tariff_id,
            title=state.title,
            last_tariff_history_id=state.last_tariff_history_id
        ).on_conflict_do_update(
            index_elements=['company_id'],
            set_={
                'valid_from': state.valid_from,
                'valid_to': state.valid_to,
                'max_employees': state.max_employees,
                'max_verifications': state.max_verifications,
                'max_orders': state.max_orders,
                'used_employees': state.used_employees or 0,
                'used_verifications': state.used_verifications or 0,
                'used_orders': state.used_orders or 0,
                'carry_over_verifications': state.carry_over_verifications,
                'carry_over_orders': state.carry_over_orders,
                'auto_manufacture_year': state.auto_manufacture_year,
                'auto_teams': state.auto_teams,
                'auto_metrolog': state.auto_metrolog,
                'base_tariff_id': state.base_tariff_id,
                'title': state.title,
                'last_tariff_history_id': state.last_tariff_history_id
            }
        ).returning(CompanyTariffState)

        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

    async def update(
        self, state: CompanyTariffState
    ) -> CompanyTariffState:
        """Обновить состояние тарифа"""
        await self.session.flush()
        await self.session.refresh(state)
        return state

    async def update_limits(
        self,
        company_id: int,
        *,
        max_verifications: Optional[int] = None,
        max_orders: Optional[int] = None,
        max_employees: Optional[int] = None,
        valid_from=None,
        valid_to=None
    ) -> bool:
        """
        Обновить лимиты через прямой UPDATE (оптимизация)
        Не требует загрузки объекта в память
        """
        values = {}
        if max_verifications is not None:
            values['max_verifications'] = max_verifications
        if max_orders is not None:
            values['max_orders'] = max_orders
        if max_employees is not None:
            values['max_employees'] = max_employees
        if valid_from is not None:
            values['valid_from'] = valid_from
        if valid_to is not None:
            values['valid_to'] = valid_to

        if not values:
            return False

        stmt = (
            update(CompanyTariffState)
            .where(CompanyTariffState.company_id == company_id)
            .values(**values)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def delete(self, company_id: int) -> bool:
        """Удалить состояние тарифа компании"""
        stmt = delete(CompanyTariffState).where(
            CompanyTariffState.company_id == company_id
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def increment_usage(
        self,
        company_id: int,
        verifications: int = 0,
        orders: int = 0,
        employees: int = 0
    ) -> bool:
        """Увеличить счётчики использования (атомарная операция)"""
        values = {}
        if verifications > 0:
            values['used_verifications'] = (
                CompanyTariffState.used_verifications + verifications
            )
        if orders > 0:
            values['used_orders'] = (
                CompanyTariffState.used_orders + orders
            )
        if employees > 0:
            values['used_employees'] = (
                CompanyTariffState.used_employees + employees
            )

        if not values:
            return False

        stmt = (
            update(CompanyTariffState)
            .where(CompanyTariffState.company_id == company_id)
            .values(**values)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def reset_counters(
        self,
        company_id: int,
        *,
        verifications: bool = False,
        orders: bool = False
    ) -> bool:
        """Сбросить счётчики использования"""
        values = {}
        if verifications:
            values['used_verifications'] = 0
        if orders:
            values['used_orders'] = 0

        if not values:
            return False

        stmt = (
            update(CompanyTariffState)
            .where(CompanyTariffState.company_id == company_id)
            .values(**values)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def check_limits(
        self, company_id: int
    ) -> Optional[dict]:
        """Проверить лимиты компании"""
        stmt = select(
            CompanyTariffState.max_verifications,
            CompanyTariffState.used_verifications,
            CompanyTariffState.max_orders,
            CompanyTariffState.used_orders,
            CompanyTariffState.max_employees,
            CompanyTariffState.used_employees
        ).where(CompanyTariffState.company_id == company_id)

        result = await self.session.execute(stmt)
        row = result.one_or_none()

        if not row:
            return None

        return {
            'max_verifications': row[0],
            'used_verifications': row[1],
            'max_orders': row[2],
            'used_orders': row[3],
            'max_employees': row[4],
            'used_employees': row[5]
        }
