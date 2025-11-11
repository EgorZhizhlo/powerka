from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from access_control import JwtData, check_tariff_access

from core.config import settings

from apps.tariff_app.services.company_tariff_service import (
    CompanyTariffService,
    get_company_tariff_service_read
)
from apps.tariff_app.services.base_tariff_service import (
    BaseTariffService,
    get_base_tariff_service_read
)


company_tariffs_frontend_router = APIRouter(
    prefix=""
)

templates = Jinja2Templates(directory="templates/tariff")


@company_tariffs_frontend_router.get(
    "/",
    response_class=HTMLResponse
)
async def companies_list_page(
    request: Request,
    user_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(get_company_tariff_service_read)
):
    """Главная страница - список всех компаний с тарифами"""
    companies_data = await service.get_all_companies_with_tariffs()

    return templates.TemplateResponse(
        "company_tariffs/list.html",
        {
            "request": request,
            "companies": companies_data,
            "user_data": user_data,
        }
    )


@company_tariffs_frontend_router.get(
    "/view/",
    response_class=HTMLResponse
)
async def company_tariff_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(get_company_tariff_service_read)
):
    """Страница текущего тарифа компании с пагинацией истории"""
    tariff_info = await service.get_company_tariff(company_id)

    offset = (page - 1) * page_size

    history_data = await service.get_tariff_history(
        company_id, limit=page_size, offset=offset
    )

    company_name = await service.get_company_name(company_id)

    return templates.TemplateResponse(
        "company_tariffs/view.html",
        {
            "request": request,
            "company_id": company_id,
            "company_name": company_name,
            "tariff_info": tariff_info,
            "history": history_data.items,
            "history_total": history_data.total,
            "history_page": history_data.page,
            "history_page_size": history_data.page_size,
            "history_total_pages": history_data.total_pages,
            "employee_data": employee_data
        }
    )


@company_tariffs_frontend_router.get(
    "/assign-page/",
    response_class=HTMLResponse
)
async def assign_tariff_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    base_tariff_service: BaseTariffService = Depends(
        get_base_tariff_service_read
    ),
    company_tariff_service: CompanyTariffService = Depends(
        get_company_tariff_service_read
    )
):
    """Страница назначения тарифа компании"""
    base_tariffs = await base_tariff_service.get_all_tariffs()
    company_name = await company_tariff_service.get_company_name(company_id)
    tariff_info = await company_tariff_service.get_company_tariff(company_id)

    return templates.TemplateResponse(
        "company_tariffs/assign.html",
        {
            "request": request,
            "company_id": company_id,
            "company_name": company_name,
            "base_tariffs": base_tariffs,
            "has_active_tariff": tariff_info.has_active_tariff,
            "employee_data": employee_data
        }
    )


@company_tariffs_frontend_router.get(
    "/edit-page/",
    response_class=HTMLResponse
)
async def edit_tariff_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_tariff_access),
    service: CompanyTariffService = Depends(get_company_tariff_service_read)
):
    """Страница изменения тарифа компании"""
    tariff_info = await service.get_company_tariff(company_id)
    company_name = await service.get_company_name(company_id)

    return templates.TemplateResponse(
        "company_tariffs/edit.html",
        {
            "request": request,
            "company_id": company_id,
            "company_name": company_name,
            "tariff_info": tariff_info,
            "employee_data": employee_data
        }
    )
