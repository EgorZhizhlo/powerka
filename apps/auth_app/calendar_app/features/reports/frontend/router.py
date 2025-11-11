from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse

from core.config import settings
from core.templates.template_manager import templates

from access_control import (
    JwtData,
    dispatchers_exception,
)

from apps.calendar_app.services import (
    CompanyService,
    get_read_company_service
)


reports_static_frontend_router = APIRouter(
    prefix='/reports/static')


@reports_static_frontend_router.get("/", response_class=HTMLResponse,)
async def view_reports(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(dispatchers_exception),
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
        "title_name": "Отчеты"
    }
    context.update(employee_data.__dict__)
    return templates.calendar.TemplateResponse(
        "reports/reports_home.html", context)
