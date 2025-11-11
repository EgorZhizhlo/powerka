from fastapi import Request, APIRouter, Query, Depends
from fastapi.responses import HTMLResponse

from core.config import settings
from core.templates.template_manager import templates

from access_control import (
    JwtData,
    check_calendar_access,
)

from apps.calendar_app.services import (
    CompanyService,
    get_read_company_service
)


orders_calendar_frontend_router = APIRouter(
    prefix=""
)


@orders_calendar_frontend_router.get("/", response_class=HTMLResponse)
async def view_orders_calendar(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
    company_service: CompanyService = Depends(get_read_company_service),
):
    # список компаний для сотрудника
    companies = await company_service.get_companies(
        employee_id=employee_data.id,
        status=employee_data.status,
    )

    # параметры календаря компании
    company_calendar_params = (
        await company_service.get_company_calendar_params(company_id)
    )

    context = {
        "request": request,
        "company_id": company_id,
        "companies": companies,
        "company_calendar_params": company_calendar_params,
        "title_name": "Календарь заявок",
        **employee_data.__dict__,
    }

    return templates.calendar.TemplateResponse(
        "orders_calendar/orders_calendar_home.html", context
    )
