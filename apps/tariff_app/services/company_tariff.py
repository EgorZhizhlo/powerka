from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from fastapi import Depends
from typing import Optional, List, Dict, Any

from infrastructure.db.session import async_session, async_db_session_begin
from models import (
    CompanyTariffHistory,
    CompanyTariffState,
    CompanyModel
)
from apps.tariff_app.repositories.company_tariff_history_repository import (
    CompanyTariffHistoryRepository
)
from apps.tariff_app.repositories.company_tariff_state_repository import (
    CompanyTariffStateRepository
)
from apps.tariff_app.repositories.base_tariff_repository import (
    BaseTariffRepository
)
from apps.tariff_app.services.base_tariff_service import (
    get_base_tariff_repository_read,
    get_base_tariff_repository_write
)
from apps.tariff_app.services.tariff_cache_service import tariff_cache
from apps.tariff_app.schemas.company_tariff import (
    CompanyTariffAssign,
    CompanyTariffUpdate,
    CompanyTariffStateResponse,
    CompanyTariffHistoryResponse,
    CompanyTariffHistoryListResponse,
    CompanyTariffFullResponse
)
from core.exceptions import NotFoundException, BadRequestException


class CompanyTariffService:
    """Сервис для работы с тарифами компаний"""

    def __init__(
        self,
        history_repo: CompanyTariffHistoryRepository,
        state_repo: CompanyTariffStateRepository,
        base_tariff_repo: BaseTariffRepository,
        session: AsyncSession
    ):
        self.history_repo = history_repo
        self.state_repo = state_repo
        self.base_tariff_repo = base_tariff_repo
        self.session = session

    async def get_company_tariff(
        self, company_id: int
    ) -> CompanyTariffFullResponse:
        """Получить полную информацию о тарифе компании"""
        state = await self.state_repo.get_by_company(company_id)
        active_history = await self.history_repo.get_active_by_company(
            company_id
        )

        return CompanyTariffFullResponse(
            state=CompanyTariffStateResponse.model_validate(state)
            if state else None,
            active_history=CompanyTariffHistoryResponse.model_validate(
                active_history
            ) if active_history else None,
            has_active_tariff=state is not None
        )

    async def get_company_name(self, company_id: int) -> str:
        """Получить название компании по ID"""
        stmt = select(CompanyModel.name).where(
            CompanyModel.id == company_id
        )
        result = await self.session.execute(stmt)
        company_name = result.scalar_one_or_none()
        return company_name or f"ID: {company_id}"

    async def get_cached_limits_info(
        self, company_id: int
    ) -> Dict[str, Any]:
        """
        Получить информацию о лимитах компании с использованием кеша

        Returns:
            Словарь с информацией о лимитах, использовании и процентах
        """
        async def fetch_from_db():
            """Callback для загрузки данных из БД"""
            state = await self.state_repo.get_by_company(company_id)
            active_history = await self.history_repo.get_active_by_company(
                company_id
            )
            return state, active_history

        return await tariff_cache.get_or_fetch_limits(
            company_id, fetch_from_db
        )

    async def get_all_companies_with_tariffs(self) -> List[Dict[str, Any]]:
        """Получить список всех компаний с информацией о тарифах"""
        stmt = (
            select(CompanyModel)
            .options(
                selectinload(CompanyModel.tariff_state),
                selectinload(CompanyModel.tariff_history),
            )
            .order_by(CompanyModel.name)
        )

        result = await self.session.execute(stmt)
        companies = result.scalars().all()

        companies_data = []
        for company in companies:
            # Получаем активную запись из истории
            active_history = None
            if company.tariff_history:
                for history in company.tariff_history:
                    if history.is_active:
                        active_history = history
                        break

            state = company.tariff_state

            company_info = {
                "id": company.id,
                "name": company.name,
                "is_active": company.is_active,
                "has_tariff": active_history is not None,
                "state": None,
            }

            if active_history and state:
                company_info["state"] = {
                    "title": state.title,
                    "valid_from": active_history.valid_from,
                    "valid_to": active_history.valid_to,
                    "max_employees": state.max_employees,
                    "used_employees": state.used_employees,
                    "max_verifications": state.max_verifications,
                    "used_verifications": state.used_verifications,
                    "max_orders": state.max_orders,
                    "used_orders": state.used_orders,
                    "auto_manufacture_year": (
                        active_history.auto_manufacture_year
                    ),
                    "auto_teams": active_history.auto_teams,
                    "auto_metrolog": active_history.auto_metrolog,
                    "carry_over_verifications": (
                        state.carry_over_verifications
                    ),
                    "carry_over_orders": state.carry_over_orders,
                }

            companies_data.append(company_info)

        return companies_data

    async def get_tariff_history(
        self,
        company_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> CompanyTariffHistoryListResponse:
        """Получить историю тарифов компании с пагинацией"""
        total = await self.history_repo.count_history_by_company(company_id)

        history = await self.history_repo.get_history_by_company(
            company_id, limit=limit, offset=offset
        )

        page_size = limit or 10
        current_page = (offset // page_size + 1) if offset and page_size else 1
        total_pages = (total + page_size - 1) // page_size if page_size else 1

        return CompanyTariffHistoryListResponse(
            items=[
                CompanyTariffHistoryResponse.model_validate(h) for h in history
            ],
            total=total,
            page=current_page,
            page_size=page_size,
            total_pages=total_pages
        )

    async def assign_tariff(
        self, company_id: int, data: CompanyTariffAssign
    ) -> CompanyTariffFullResponse:
        """
        Назначить новый тариф компании
        (с блокировкой для предотвращения race conditions)
        """
        # Валидация уже выполнена в схеме CompanyTariffAssign

        base_tariff = await self.base_tariff_repo.get_by_id(
            data.base_tariff_id
        )
        if not base_tariff:
            raise NotFoundException(
                detail=f"Базовый тариф {data.base_tariff_id} не найден"
            )

        state = await self.state_repo.get_by_company(
            company_id, for_update=True
        )

        await self.history_repo.deactivate_previous(
            company_id, reason="Назначен новый тариф"
        )

        if data.valid_from:
            from datetime import timedelta
            await self.history_repo.close_previous_tariff(
                company_id,
                data.valid_from - timedelta(days=1)
            )

        history = CompanyTariffHistory(
            company_id=company_id,
            base_tariff_id=data.base_tariff_id,
            title=base_tariff.title,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            max_employees=data.max_employees,
            monthly_verifications=data.monthly_verifications,
            monthly_orders=data.monthly_orders,
            auto_manufacture_year=data.auto_manufacture_year,
            auto_teams=data.auto_teams,
            auto_metrolog=data.auto_metrolog,
            reason=data.reason,
            is_active=True
        )
        history = await self.history_repo.create(history)

        # Вычисляем новые лимиты на основе периода
        new_max_verifications = None
        new_max_orders = None

        if data.valid_to:
            months = (data.valid_to - data.valid_from).days // 30
            if months > 0:
                if data.monthly_verifications is not None:
                    new_max_verifications = (
                        data.monthly_verifications * months
                    )
                if data.monthly_orders is not None:
                    new_max_orders = data.monthly_orders * months
            else:
                new_max_verifications = data.monthly_verifications
                new_max_orders = data.monthly_orders
        else:
            new_max_verifications = data.monthly_verifications
            new_max_orders = data.monthly_orders

        # Если установлены флаги переноса и есть существующий state,
        # добавляем новые лимиты к существующим
        state_max_verifications = new_max_verifications
        state_max_orders = new_max_orders

        if state:
            if (data.carry_over_verifications
                    and new_max_verifications is not None):
                existing_max = state.max_verifications or 0
                state_max_verifications = new_max_verifications + existing_max
            
            if data.carry_over_orders and new_max_orders is not None:
                existing_max = state.max_orders or 0
                state_max_orders = new_max_orders + existing_max

        from apps.company_app.common import (
            validate_and_sync_limits, calculate_actual_usage
        )

        await validate_and_sync_limits(
            self.session,
            company_id,
            data.max_employees,
            state_max_verifications,
            state_max_orders
        )

        actual_employees, actual_verifications, actual_orders = (
            await calculate_actual_usage(self.session, company_id)
        )

        new_state = CompanyTariffState(
            company_id=company_id,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            max_employees=data.max_employees,
            max_verifications=state_max_verifications,
            max_orders=state_max_orders,
            used_employees=actual_employees,
            used_verifications=actual_verifications,
            used_orders=actual_orders,
            carry_over_verifications=data.carry_over_verifications,
            carry_over_orders=data.carry_over_orders,
            auto_manufacture_year=data.auto_manufacture_year,
            auto_teams=data.auto_teams,
            auto_metrolog=data.auto_metrolog,
            base_tariff_id=data.base_tariff_id,
            title=base_tariff.title,
            last_tariff_history_id=history.id
        )
        state = await self.state_repo.upsert(new_state)

        await self._sync_company_settings(
            company_id,
            data.auto_manufacture_year,
            data.auto_teams,
            data.auto_metrolog,
            is_active=True
        )

        await tariff_cache.invalidate_cache(company_id)
        await tariff_cache.set_cached_limits(company_id, state)

        return CompanyTariffFullResponse(
            state=CompanyTariffStateResponse.model_validate(state),
            active_history=CompanyTariffHistoryResponse.model_validate(
                history
            ),
            has_active_tariff=True
        )

    async def update_tariff(
        self, company_id: int, data: CompanyTariffUpdate
    ) -> CompanyTariffFullResponse:
        """
        Изменить/продлить текущий тариф компании
        (с блокировкой для предотвращения race conditions)
        """
        state = await self.state_repo.get_by_company(
            company_id, for_update=True
        )
        if not state:
            raise NotFoundException(
                detail=f"У компании {company_id} нет активного тарифа"
            )

        # Получаем текущую историю
        active_history = await self.history_repo.get_active_by_company(
            company_id, for_update=True
        )

        # Деактивируем предыдущую историю
        if active_history:
            await self.history_repo.deactivate_previous(company_id)

        # Определяем новые даты
        final_valid_from = (
            data.valid_from if data.valid_from is not None
            else state.valid_from
        )
        final_valid_to = (
            data.valid_to if data.valid_to is not None
            else state.valid_to
        )

        # Создаем новую запись в истории
        new_history = CompanyTariffHistory(
            company_id=company_id,
            base_tariff_id=state.base_tariff_id,
            title=state.title,
            valid_from=final_valid_from,
            valid_to=final_valid_to,
            max_employees=(
                data.max_employees if data.max_employees is not None
                else state.max_employees
            ),
            monthly_verifications=data.monthly_verifications,
            monthly_orders=data.monthly_orders,
            auto_manufacture_year=(
                data.auto_manufacture_year
                if data.auto_manufacture_year is not None
                else state.auto_manufacture_year
            ),
            auto_teams=(
                data.auto_teams if data.auto_teams is not None
                else state.auto_teams
            ),
            auto_metrolog=(
                data.auto_metrolog if data.auto_metrolog is not None
                else state.auto_metrolog
            ),
            reason=data.reason,
            is_active=True
        )
        new_history = await self.history_repo.create(new_history)

        # Пересчитываем max_verifications и max_orders
        final_max_verifications = None
        final_max_orders = None

        if final_valid_to and final_valid_from:
            delta_days = (final_valid_to - final_valid_from).days
            months = max(delta_days // 30, 0)

            if new_history.monthly_verifications is not None:
                final_max_verifications = (
                    new_history.monthly_verifications * months
                )

            if new_history.monthly_orders is not None:
                final_max_orders = new_history.monthly_orders * months

        # Обновляем state
        state.valid_from = final_valid_from
        state.valid_to = final_valid_to
        state.max_employees = new_history.max_employees
        state.max_verifications = final_max_verifications
        state.max_orders = final_max_orders

        if data.auto_manufacture_year is not None:
            state.auto_manufacture_year = data.auto_manufacture_year
        if data.auto_teams is not None:
            state.auto_teams = data.auto_teams
        if data.auto_metrolog is not None:
            state.auto_metrolog = data.auto_metrolog

        state.last_tariff_history_id = new_history.id

        # Валидация финальных лимитов против фактического использования
        from apps.company_app.common import validate_and_sync_limits

        await validate_and_sync_limits(
            self.session,
            company_id,
            state.max_employees,
            final_max_verifications,
            final_max_orders
        )

        state = await self.state_repo.update(state)

        await self._sync_company_settings(
            company_id,
            state.auto_manufacture_year,
            state.auto_teams,
            state.auto_metrolog,
            is_active=True
        )

        # Инвалидируем старый кеш и обновляем
        await tariff_cache.invalidate_cache(company_id)
        await tariff_cache.set_cached_limits(company_id, state)

        return CompanyTariffFullResponse(
            state=CompanyTariffStateResponse.model_validate(state),
            active_history=CompanyTariffHistoryResponse.model_validate(
                new_history
            ),
            has_active_tariff=True
        )

    async def delete_tariff(self, company_id: int) -> None:
        """
        Удалить тариф компании полностью
        (с блокировкой для предотвращения race conditions)
        """
        state = await self.state_repo.get_by_company(
            company_id, for_update=True
        )
        if not state:
            raise NotFoundException(
                detail=f"У компании {company_id} нет активного тарифа"
            )

        await self.history_repo.deactivate_previous(company_id)

        await self.state_repo.delete(company_id)

        await self._sync_company_settings(
            company_id,
            auto_manufacture_year=False,
            auto_teams=False,
            auto_metrolog=False,
            is_active=False
        )

        # Инвалидируем кеш после удаления тарифа
        await tariff_cache.invalidate_cache(company_id)

    async def increment_usage_with_cache(
        self,
        company_id: int,
        field: str,
        delta: int = 1
    ) -> bool:
        """
        Увеличить счётчик использования в БД и обновить кеш

        Args:
            company_id: ID компании
            field: Поле для обновления (employees/verifications/orders)
            delta: Изменение значения (по умолчанию +1)

        Returns:
            True если обновление прошло успешно
        """
        # Обновляем в БД
        kwargs = {field: delta}
        success = await self.state_repo.increment_usage(
            company_id, **kwargs
        )

        # Обновляем кеш
        if success:
            await tariff_cache.update_usage(company_id, field, delta)

        return success

    async def _sync_company_settings(
        self,
        company_id: int,
        auto_manufacture_year: bool,
        auto_teams: bool,
        auto_metrolog: bool,
        is_active: bool
    ) -> None:
        """
        Синхронизировать настройки компании
        (флаги автоматизации + статус активности)
        """
        from sqlalchemy import select
        from models import EmployeeModel
        from access_control.token_versioning import bump_jwt_token_version

        stmt = (
            update(CompanyModel)
            .where(CompanyModel.id == company_id)
            .values(
                auto_manufacture_year=auto_manufacture_year,
                auto_teams=auto_teams,
                auto_metrolog=auto_metrolog,
                is_active=is_active
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

        # Получаем всех сотрудников компании для инвалидации токенов
        stmt = (
            select(EmployeeModel.id)
            .join(EmployeeModel.companies)
            .where(CompanyModel.id == company_id)
        )
        result = await self.session.execute(stmt)
        employee_ids = result.scalars().all()

        # Обновляем версию токенов всех сотрудников компании
        # (включая админов - они тоже должны обновиться)
        for emp_id in employee_ids:
            await bump_jwt_token_version(f"user:{emp_id}:company_version")


async def get_company_tariff_history_repo_read(
    session: AsyncSession = Depends(async_session)
) -> CompanyTariffHistoryRepository:
    return CompanyTariffHistoryRepository(session)


async def get_company_tariff_history_repo_write(
    session: AsyncSession = Depends(async_db_session_begin)
) -> CompanyTariffHistoryRepository:
    return CompanyTariffHistoryRepository(session)


async def get_company_tariff_state_repo_read(
    session: AsyncSession = Depends(async_session)
) -> CompanyTariffStateRepository:
    return CompanyTariffStateRepository(session)


async def get_company_tariff_state_repo_write(
    session: AsyncSession = Depends(async_db_session_begin)
) -> CompanyTariffStateRepository:
    return CompanyTariffStateRepository(session)


# Dependencies для получения сервиса
async def get_company_tariff_service_read(
    history_repo: CompanyTariffHistoryRepository = Depends(
        get_company_tariff_history_repo_read
    ),
    state_repo: CompanyTariffStateRepository = Depends(
        get_company_tariff_state_repo_read
    ),
    base_tariff_repo: BaseTariffRepository = Depends(
        get_base_tariff_repository_read
    ),
    session: AsyncSession = Depends(async_session)
) -> CompanyTariffService:
    return CompanyTariffService(
        history_repo, state_repo, base_tariff_repo, session
    )


async def get_company_tariff_service_write(
    history_repo: CompanyTariffHistoryRepository = Depends(
        get_company_tariff_history_repo_write
    ),
    state_repo: CompanyTariffStateRepository = Depends(
        get_company_tariff_state_repo_write
    ),
    base_tariff_repo: BaseTariffRepository = Depends(
        get_base_tariff_repository_write
    ),
    session: AsyncSession = Depends(async_db_session_begin)
) -> CompanyTariffService:
    return CompanyTariffService(
        history_repo, state_repo, base_tariff_repo, session
    )
