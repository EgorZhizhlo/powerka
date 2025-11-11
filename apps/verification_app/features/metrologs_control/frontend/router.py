from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from access_control import (
    JwtData,
    check_active_access_verification)

from core.config import settings, format_date
from apps.verification_app.exceptions import (
    CustomVerificationVerifierException,

    CustomCreateMetrologInfoAccessException,
    CustomUpdateMetrologInfoAccessException,
)

from apps.verification_app.common import check_equip_conditions
from apps.verification_app.repositories import (
    MetrologInfoRepository, read_metrolog_info_repository,
    CompanyRepository, read_company_repository
)
from apps.verification_app.schemas.metrologs_control_f import MetrologInfoForm


metrologs_control_frontend_router = APIRouter(prefix='/metrologs-control')
templates = Jinja2Templates(
    directory="templates/verification")

templates.env.filters['strftime'] = format_date


@metrologs_control_frontend_router.get(
    "/create",
    response_class=HTMLResponse
)
async def create_metrolog_info_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    metrolog_info_repo: MetrologInfoRepository = Depends(
        read_metrolog_info_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    check_exist_metrolog = await metrolog_info_repo.check_exist_metrolog_info(
        verification_entry_id=verification_entry_id
    )
    if check_exist_metrolog:
        raise CustomCreateMetrologInfoAccessException(company_id=company_id)

    verification_entry = await metrolog_info_repo.get_for_create(
        verification_entry_id=verification_entry_id,
        employee_id=employee_id, status=status
    )

    if not verification_entry:
        raise CustomCreateMetrologInfoAccessException(company_id=company_id)
    if not verification_entry.verifier_id:
        raise CustomVerificationVerifierException(company_id=company_id)
    check_equip_conditions(
        verification_entry.equipments, for_view=True,
        company_id=company_id)

    context = {
        "request": request,
        "company_id": company_id,
        "title_name": f"Создание протокола поверки №{verification_entry_id}",
        "verification_entry_id": verification_entry_id,
        "metrolog_info": MetrologInfoForm.empty().model_dump(),
        "companies": await company_repo.get_companies_for_user(
            status=status,
            employee_id=employee_id
        ),
        "reason": verification_entry.reason
    }
    context.update(employee_data.__dict__)

    return templates.TemplateResponse(
        "metrologs_control/create.html",
        context
    )


@metrologs_control_frontend_router.get(
    "/update",
    response_class=HTMLResponse
)
async def update_metrolog_info_page(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    metrolog_info_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    metrolog_info_repo: MetrologInfoRepository = Depends(
        read_metrolog_info_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    metrolog_info = await metrolog_info_repo.get_for_update(
        metrolog_info_id=metrolog_info_id,
        verification_entry_id=verification_entry_id,
        employee_id=employee_id, status=status
    )
    if not metrolog_info:
        raise CustomUpdateMetrologInfoAccessException(company_id=company_id)

    if not metrolog_info.verification.verifier_id:
        raise CustomVerificationVerifierException(company_id=company_id)

    check_equip_conditions(
        metrolog_info.verification.equipments, for_view=True,
        company_id=company_id)

    context = {
        "request": request,
        "company_id": company_id,
        "verification_entry_id": verification_entry_id,
        "title_name": f"Редактирование протокола поверки №{
            verification_entry_id}",
        "metrolog_info": metrolog_info,
        "reason": metrolog_info.verification.reason,
        "companies": await company_repo.get_companies_for_user(
            status=status,
            employee_id=employee_id
        ),
    }
    context.update(employee_data.__dict__)

    return templates.TemplateResponse(
        "metrologs_control/update.html",
        context
    )
