from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse

from core.config import settings
from core.templates.template_manager import templates

from access_control import (
    JwtData,
    dispatcher2_exception
)

from apps.calendar_app.services import (
    CompanyService,
    get_read_company_service
)


orders_planning_frontend_router = APIRouter(prefix="/planning")


@orders_planning_frontend_router.get(
    "/",
    response_class=HTMLResponse)
async def view_orders_planning(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(dispatcher2_exception),
    company_service: CompanyService = Depends(get_read_company_service),
):
    # список компаний для сотрудника
    companies = await company_service.get_companies(
        employee_id=employee_data.id,
        status=employee_data.status,
    )

    context = {
        "request": request,
        "company_id": company_id,
        "companies": companies,
        "title_name": "Порядок заявок"
    }
    context.update(employee_data.__dict__)
    return templates.calendar.TemplateResponse(
        "orders_planning/orders_planning_home.html", context)
