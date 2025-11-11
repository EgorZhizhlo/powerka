from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import settings

from access_control import JwtData, check_tariff_access

from apps.tariff_app.services.base_tariff_service import (
    BaseTariffService,
    get_base_tariff_service_read
)


base_tariffs_frontend_router = APIRouter(
    prefix="/base-tariffs")

templates = Jinja2Templates(directory="templates/tariff")


@base_tariffs_frontend_router.get(
    "/",
    response_class=HTMLResponse
)
async def base_tariffs_page(
    request: Request,
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_read)
):
    """
    Страница со списком базовых тарифов и управлением ими.

    Требует права доступа к управлению тарифами.
    """
    tariffs = await service.get_all_tariffs()

    return templates.TemplateResponse(
        "base_tariffs/list.html",
        {
            "request": request,
            "tariffs": tariffs,
            "employee_data": employee_data
        }
    )


@base_tariffs_frontend_router.get(
    "/create/",
    response_class=HTMLResponse
)
async def create_base_tariff_page(
    request: Request,
    employee_data: JwtData = Depends(check_tariff_access)
):
    """
    Страница с формой создания нового базового тарифа.

    Требует права доступа к управлению тарифами.
    """
    return templates.TemplateResponse(
        "base_tariffs/create.html",
        {
            "request": request,
            "employee_data": employee_data
        }
    )


@base_tariffs_frontend_router.get(
    "/edit/",
    response_class=HTMLResponse
)
async def edit_base_tariff_page(
    request: Request,
    tariff_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: BaseTariffService = Depends(get_base_tariff_service_read)
):
    """
    Страница с формой редактирования базового тарифа.

    Требует права доступа к управлению тарифами.
    """
    tariff = await service.get_tariff_by_id(tariff_id)

    return templates.TemplateResponse(
        "base_tariffs/edit.html",
        {
            "request": request,
            "tariff": tariff,
            "employee_data": employee_data
        }
    )
