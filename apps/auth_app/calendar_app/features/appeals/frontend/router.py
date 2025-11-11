from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse

from core.config import settings
from core.templates.template_manager import templates


from access_control import (
    JwtData,
    dispatcher2_exception,
)

from models.enums import map_appeal_status_to_label
from apps.calendar_app.services import (
    CompanyService,
    get_read_company_service
)


appeals_frontend_router = APIRouter(
    prefix="/appeals"
)


@appeals_frontend_router.get("/", response_class=HTMLResponse)
async def view_appeals(
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

    # параметры календаря компании
    company_calendar_params = (
        await company_service.get_company_calendar_params(company_id)
    )

    context = {
        "request": request,
        "company_id": company_id,
        "companies": companies,
        "map_of_status": map_appeal_status_to_label,
        "title_name": "Обращения",
        **company_calendar_params,
        **employee_data.__dict__
    }

    return templates.calendar.TemplateResponse(
        "appeals/appeals_home.html", context
    )
