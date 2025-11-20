from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
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

    async def create_state(
        self, state: CompanyTariffState
    ) -> CompanyTariffState:
        """Создать состояние тарифа"""
        self.session.add(state)
        await self.session.flush()
        await self.session.refresh(state)
        return state

    async def upsert_state(
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

    async def update_state(
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
        """Обновляет лимиты тарифа с блокировкой строки."""
        state = await self.get_by_company(company_id, for_update=True)
        if not state:
            return False

        if max_verifications is not None:
            state.max_verifications = max_verifications

        if max_orders is not None:
            state.max_orders = max_orders

        if max_employees is not None:
            state.max_employees = max_employees

        if valid_from is not None:
            state.valid_from = valid_from

        if valid_to is not None:
            state.valid_to = valid_to

        await self.session.flush()
        return True

    async def delete_state(self, company_id: int) -> bool:
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
        """Безопасно увеличивает usage с блокировкой строки."""
        state = await self.get_by_company(company_id, for_update=True)
        if not state:
            return False

        if verifications > 0:
            state.used_verifications = state.used_verifications or 0
            state.used_verifications = state.used_verifications + verifications

        if orders > 0:
            state.used_orders = state.used_orders or 0
            state.used_orders = state.used_orders + orders

        if employees > 0:
            state.used_employees = state.used_employees or 0
            state.used_employees = state.used_employees + employees

        await self.session.flush()
        return True

    async def reset_counters(
        self,
        company_id: int,
        *,
        verifications: bool = False,
        orders: bool = False
    ) -> bool:
        """Сбрасывает счётчики использования с блокировкой строки."""
        state = await self.get_by_company(company_id, for_update=True)
        if not state:
            return False

        if verifications:
            state.used_verifications = 0

        if orders:
            state.used_orders = 0

        await self.session.flush()
        return True

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

    async def decrement_usage_safe(
        self,
        company_id: int,
        *,
        verifications: int = 0,
        orders: int = 0,
        employees: int = 0
    ) -> bool:
        """
        Безопасное уменьшение usage:
        - SELECT ... FOR UPDATE (гарантия блокировок)
        - Исключает фантомы и write-skew
        - Не уходит в минус
        """

        state = await self.get_by_company(company_id, for_update=True)
        if not state:
            return False

        if verifications:
            state.used_verifications = max(
                0,
                (state.used_verifications or 0) - verifications
            )

        if orders:
            state.used_orders = max(
                0,
                (state.used_orders or 0) - orders
            )

        if employees:
            state.used_employees = max(
                0,
                (state.used_employees or 0) - employees
            )

        await self.session.flush()
        return True

    async def count_actual_employees(self, company_id: int) -> int:
        """Подсчитать количество сотрудников."""
        from models import (
            EmployeeModel,
            CompanyModel
        )
        stmt = (
            select(func.count(EmployeeModel.id))
            .where(
                EmployeeModel.companies.any(CompanyModel.id == company_id),
                EmployeeModel.is_deleted.is_not(True)
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one()

    async def calculate_actual_usage(
        self, company_id: int
    ) -> tuple[int, int, int]:
        """Подсчитать фактическое использование лимитов компании."""
        from models import (
            VerificationEntryModel,
            OrderModel,
        )
        employees_count = await self.count_actual_employees(company_id)

        verifications_stmt = (
            select(func.count(VerificationEntryModel.id))
            .where(VerificationEntryModel.company_id == company_id)
        )
        verifications_count = (
            await self.session.execute(verifications_stmt)
        ).scalar_one()

        orders_stmt = (
            select(func.count(OrderModel.id))
            .where(
                OrderModel.company_id == company_id,
                OrderModel.is_active.is_(True),
            )
        )
        orders_count = (
            await self.session.execute(orders_stmt)
        ).scalar_one()

        return employees_count, verifications_count, orders_count

    async def validate_and_sync_limits(
        self,
        company_id: int,
        max_employees: int | None,
        max_verifications: int | None,
        max_orders: int | None
    ) -> None:
        from core.exceptions.api.tariff_control import TariffForbiddenError
        actual_employees, actual_verifications, actual_orders = (
            await self.calculate_actual_usage(company_id)
        )

        errors = []

        if max_employees is not None and actual_employees > max_employees:
            errors.append(
                f"Сотрудников: {actual_employees} > лимит {max_employees}"
            )

        if max_verifications is not None and actual_verifications > max_verifications:
            errors.append(
                f"Поверок: {actual_verifications} > лимит {max_verifications}"
            )

        if max_orders is not None and actual_orders > max_orders:
            errors.append(
                f"Заявок: {actual_orders} > лимит {max_orders}"
            )

        if errors:
            raise TariffForbiddenError(
                detail=(
                    "Невозможно назначить тариф: "
                    "фактическое использование превышает лимиты. "
                    + "; ".join(errors)
                )
            )
