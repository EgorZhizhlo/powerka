from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from typing import List

from infrastructure.db.session import async_session, async_db_session_begin
from models import BaseTariff
from apps.tariff_app.repositories.base_tariff_repository import BaseTariffRepository
from apps.tariff_app.schemas.base_tariff import (
    BaseTariffCreate,
    BaseTariffUpdate,
    BaseTariffResponse
)
from core.exceptions import BadRequestException, NotFoundException


class BaseTariffService:
    """Сервис для работы с базовыми тарифами"""

    def __init__(self, repository: BaseTariffRepository):
        self.repository = repository

    async def get_all_tariffs(self) -> List[BaseTariffResponse]:
        """Получить все базовые тарифы"""
        tariffs = await self.repository.get_all()
        return [BaseTariffResponse.model_validate(t) for t in tariffs]

    async def get_tariff_by_id(self, tariff_id: int) -> BaseTariffResponse:
        """Получить базовый тариф по ID"""
        tariff = await self.repository.get_by_id(tariff_id)
        if not tariff:
            raise NotFoundException(
                detail=f"Базовый тариф с ID {tariff_id} не найден"
            )
        return BaseTariffResponse.model_validate(tariff)

    async def create_tariff(self, data: BaseTariffCreate) -> BaseTariffResponse:
        """Создать новый базовый тариф"""
        # Проверка уникальности названия
        if await self.repository.exists_by_title(data.title):
            raise BadRequestException(
                detail=f"Тариф с названием '{data.title}' уже существует"
            )

        # Создание тарифа
        tariff = BaseTariff(
            title=data.title,
            description=data.description,
            max_employees=data.max_employees,
            max_verifications_per_month=data.max_verifications_per_month,
            max_orders_per_month=data.max_orders_per_month,
            auto_manufacture_year=data.auto_manufacture_year,
            auto_teams=data.auto_teams,
            auto_metrolog=data.auto_metrolog
        )

        tariff = await self.repository.create(tariff)
        return BaseTariffResponse.model_validate(tariff)

    async def update_tariff(
        self,
        tariff_id: int,
        data: BaseTariffUpdate
    ) -> BaseTariffResponse:
        """Обновить существующий базовый тариф"""
        tariff = await self.repository.get_by_id(tariff_id)
        if not tariff:
            raise NotFoundException(
                detail=f"Базовый тариф с ID {tariff_id} не найден"
            )

        # Проверка уникальности названия (если меняется)
        if data.title and data.title != tariff.title:
            if await self.repository.exists_by_title(data.title, exclude_id=tariff_id):
                raise BadRequestException(
                    detail=f"Тариф с названием '{data.title}' уже существует"
                )

        # Обновление полей
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tariff, field, value)

        tariff = await self.repository.update(tariff)
        return BaseTariffResponse.model_validate(tariff)

    async def delete_tariff(self, tariff_id: int) -> None:
        """Удалить базовый тариф"""
        tariff = await self.repository.get_by_id(tariff_id)
        if not tariff:
            raise NotFoundException(
                detail=f"Базовый тариф с ID {tariff_id} не найден"
            )

        success = await self.repository.delete(tariff_id)
        if not success:
            raise BadRequestException(
                detail="Не удалось удалить тариф"
            )


# Dependency для получения репозитория (чтение)
async def get_base_tariff_repository_read(
    session: AsyncSession = Depends(async_session)
) -> BaseTariffRepository:
    """Получить репозиторий для чтения базовых тарифов"""
    return BaseTariffRepository(session)


# Dependency для получения репозитория (запись)
async def get_base_tariff_repository_write(
    session: AsyncSession = Depends(async_db_session_begin)
) -> BaseTariffRepository:
    """Получить репозиторий для записи базовых тарифов"""
    return BaseTariffRepository(session)


# Dependency для получения сервиса (чтение)
async def get_base_tariff_service_read(
    repository: BaseTariffRepository = Depends(get_base_tariff_repository_read)
) -> BaseTariffService:
    """Получить сервис для чтения базовых тарифов"""
    return BaseTariffService(repository)


# Dependency для получения сервиса (запись)
async def get_base_tariff_service_write(
    repository: BaseTariffRepository = Depends(
        get_base_tariff_repository_write)
) -> BaseTariffService:
    """Получить сервис для записи базовых тарифов"""
    return BaseTariffService(repository)
