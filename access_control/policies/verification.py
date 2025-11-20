from typing import Optional
from fastapi import Depends, Cookie, Query

from models.enums import EmployeeStatus

from core.config import settings
from core.exceptions.base import RedirectHttpException
from core.exceptions.app.common import ForbiddenError

from access_control.tokens import (
    JwtData,
    build_jwt_data,
    check_jwt_data
)
from access_control.roles import (
    validate_company_access,

    access_verification,

    verifier,
    auditor_verifier
)


login_url = settings.login_url
redirect_to_calendar = {
    EmployeeStatus.dispatcher1,
    EmployeeStatus.dispatcher2
}


async def check_access_verification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    auth_token: Optional[str] = Cookie(None),
    company_info_token: Optional[str] = Cookie(None),
) -> JwtData:
    user_data, comp_data = check_jwt_data(
        auth_token, company_info_token)

    user_data_status = user_data.get("status")

    if user_data_status not in access_verification:
        active_ids = set(comp_data.get("active_company_ids", []))
        if not active_ids:
            raise ForbiddenError(company_id=company_id)

        first_cid = min(active_ids)
        if user_data_status in redirect_to_calendar:
            url = f"/calendar/{first_cid}"
        else:
            url = settings.login_url

        raise RedirectHttpException(redirect_to_url=url)

    employee_data = build_jwt_data(user_data, comp_data)

    validate_company_access(
        company_id, employee_data, "verification", active=False)

    # Всё ок, собираем и возвращаем модель
    return employee_data


async def check_active_access_verification(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_access_verification),
):
    validate_company_access(
        company_id, employee_data, "verification", active=True)
    return employee_data


async def verifier_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_access_verification),
):
    if employee_data.status in verifier:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def auditor_verifier_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_access_verification),
):
    if employee_data.status in auditor_verifier:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def active_verifier_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_verification),
):
    if employee_data.status in verifier:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def active_auditor_verifier_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_verification),
):
    if employee_data.status in auditor_verifier:
        raise ForbiddenError(company_id=company_id)
    return employee_data
