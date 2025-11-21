from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates

from access_control import JwtData, auditor_verifier_exception

from core.config import settings
from core.exceptions.frontend import InternalServerError


from apps.verification_app.repositories import (
    CompanyRepository, read_company_repository,
    ActSeriesRepository, read_act_series_repository,
)


reports_frontend_router = APIRouter(prefix='/reports')
templates = Jinja2Templates(directory="templates/verification")


async def get_column_labels(company):
    column_labels = {
        "checkbox_1": company.additional_checkbox_1,
        "checkbox_2": company.additional_checkbox_2,
        "checkbox_3": company.additional_checkbox_3,
        "checkbox_4": company.additional_checkbox_4,
        "checkbox_5": company.additional_checkbox_5,
    }
    return column_labels


@reports_frontend_router.get("/act-numbers")
async def act_number_report_view(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    act_series_repo: ActSeriesRepository = Depends(
        read_act_series_repository
    )
):
    """Отчет по номерам актов - только шаблон."""
    try:
        status = employee_data.status
        employee_id = employee_data.id

        companies = await company_repo.get_companies_for_user(
            status=status,
            employee_id=employee_id
        )
        company_name = next(
            (
                company.name
                for company in companies
                if company.id == company_id
            ), ""
        )

        act_series = await act_series_repo.get_act_series_for_company()

        context = {
            "request": request,
            "company_id": company_id,
            "title_name": (
                f"Статистика по номерам актов компании: {company_name}"
            ),
            "companies": companies,
            "series": act_series
        }
        context.update(employee_data.__dict__)

        return templates.TemplateResponse(
            "reports/act_numbers.html",
            context
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_frontend_router.get("/employees")
async def employees_report_view(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    company_repo: CompanyRepository = Depends(read_company_repository),
):
    """Отчет по сотрудникам компании - только шаблон."""
    try:
        status = employee_data.status
        employee_id = employee_data.id

        # Получаем список компаний через репозиторий
        companies = await company_repo.get_companies_for_user(
            employee_id=employee_id,
            status=status
        )
        company_name = next(
            (
                company.name
                for company in companies
                if company.id == company_id
            ), ""
        )

        # Получаем данные компании для названий чекбоксов
        company = await company_repo.get_company_additional_checkboxes()

        context = {
            "request": request,
            "company_id": company_id,
            "title_name": (
                f"Статистика по сотрудникам компании: {company_name}"
            ),
            "companies": companies,
            "column_labels": await get_column_labels(company),
        }
        context.update(employee_data.__dict__)

        return templates.TemplateResponse(
            "reports/employees.html", context
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )


@reports_frontend_router.get("/cities")
async def cities_report_view(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    company_repo: CompanyRepository = Depends(read_company_repository),
):
    """Отчет по городам компании - только шаблон."""
    try:
        status = employee_data.status
        employee_id = employee_data.id

        # Получаем список компаний через репозиторий
        companies = await company_repo.get_companies_for_user(
            employee_id=employee_id,
            status=status
        )
        company_name = next(
            (
                company.name
                for company in companies
                if company.id == company_id
            ), ""
        )

        # Получаем данные компании для названий чекбоксов
        company = await company_repo.get_company_additional_checkboxes()

        context = {
            "request": request,
            "company_id": company_id,
            "title_name": (
                f"Статистика по населенным пунктам компании: {company_name}"
            ),
            "companies": companies,
            "column_labels": await get_column_labels(company),
            "model_type": "cities",
        }
        context.update(employee_data.__dict__)

        return templates.TemplateResponse(
            "reports/cities.html", context
        )
    except Exception as ex:
        raise InternalServerError(
            detail=str(ex),
            company_id=company_id
        )
