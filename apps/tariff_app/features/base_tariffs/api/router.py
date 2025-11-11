from fastapi import APIRouter, Depends, Query, Body, status

from access_control import JwtData, check_tariff_access

from core.config import settings

from apps.tariff_app.schemas import (
    BaseTariffCreate,
    BaseTariffUpdate,
    BaseTariffResponse,
    BaseTariffListResponse
)
from apps.tariff_app.services import (
    BaseTariffService,
    get_base_tariff_service_read,
    get_base_tariff_service_write
)


base_tariffs_api_router = APIRouter(
    prefix="/api/base-tariffs")


@base_tariffs_api_router.get(
    "/",
    response_model=BaseTariffListResponse
)
async def get_all_base_tariffs(
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_read)
):
    """
    Получить список всех базовых тарифных планов.

    Требует права доступа к управлению тарифами.
    """
    tariffs = await service.get_all_tariffs()
    return BaseTariffListResponse(tariffs=tariffs, total=len(tariffs))


@base_tariffs_api_router.get(
    "/details",
    response_model=BaseTariffResponse
)
async def get_base_tariff_by_id(
    tariff_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_read)
):
    """
    Получить детальную информацию о базовом тарифе по его ID.

    Требует права доступа к управлению тарифами.
    """
    return await service.get_tariff_by_id(tariff_id)


@base_tariffs_api_router.post(
    "/",
    response_model=BaseTariffResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_base_tariff(
    data: BaseTariffCreate = Body(...),
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_write)
):
    """
    Создать новый базовый тарифный план.

    Требует права доступа к управлению тарифами.
    """
    return await service.create_tariff(data)


@base_tariffs_api_router.put(
    "/",
    response_model=BaseTariffResponse
)
async def update_base_tariff(
    tariff_id: int = Query(..., ge=1, le=settings.max_int),
    data: BaseTariffUpdate = Body(...),
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_write)
):
    """
    Обновить существующий базовый тарифный план.

    Требует права доступа к управлению тарифами.
    """
    return await service.update_tariff(tariff_id, data)


@base_tariffs_api_router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_base_tariff(
    tariff_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_write)
):
    """
    Удалить базовый тарифный план.

    Требует права доступа к управлению тарифами.
    """
    await service.delete_tariff(tariff_id)
