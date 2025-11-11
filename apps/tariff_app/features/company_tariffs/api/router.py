from fastapi import APIRouter, Depends, Query, Body, status

from access_control import JwtData, check_tariff_access

from core.config import settings

from apps.tariff_app.schemas.company_tariff import (
    CompanyTariffAssign,
    CompanyTariffUpdate,
    CompanyTariffFullResponse,
    CompanyTariffHistoryListResponse
)
from apps.tariff_app.services.company_tariff_service import (
    CompanyTariffService,
    get_company_tariff_service_read,
    get_company_tariff_service_write
)


company_tariffs_api_router = APIRouter(
    prefix="/api/company-tariffs"
)


@company_tariffs_api_router.get(
    "/",
    response_model=CompanyTariffFullResponse
)
async def get_company_tariff(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(
        get_company_tariff_service_read
    )
):
    """Получить текущий тариф и состояние компании"""
    return await service.get_company_tariff(company_id)


@company_tariffs_api_router.get(
    "/history",
    response_model=CompanyTariffHistoryListResponse
)
async def get_company_tariff_history(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(
        get_company_tariff_service_read
    )
):
    """Получить историю тарифов компании с пагинацией"""
    offset = (page - 1) * page_size
    return await service.get_tariff_history(
        company_id, limit=page_size, offset=offset
    )


@company_tariffs_api_router.post(
    "/",
    response_model=CompanyTariffFullResponse,
    status_code=status.HTTP_201_CREATED
)
async def assign_company_tariff(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    data: CompanyTariffAssign = Body(...),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(
        get_company_tariff_service_write
    )
):
    """
    Назначить тариф компании.

    Можно назначить на основе базового тарифа или создать кастомный.
    При назначении создаётся запись в истории и обновляется текущее состояние.
    """
    return await service.assign_tariff(company_id, data)


@company_tariffs_api_router.put(
    "/",
    response_model=CompanyTariffFullResponse
)
async def update_company_tariff(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    data: CompanyTariffUpdate = Body(...),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(
        get_company_tariff_service_write
    )
):
    """
    Изменить текущий тариф компании.

    Создаёт новую запись в истории и обновляет текущее состояние.
    """
    return await service.update_tariff(company_id, data)


@company_tariffs_api_router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_company_tariff(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(
        get_company_tariff_service_write
    )
):
    """
    Удалить тариф компании.

    Деактивирует все записи в истории и удаляет состояние тарифа.
    Компания останется без тарифа.
    """
    await service.delete_tariff(company_id)
    return None
