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

    access_calendar,

    dispatcher2,
    dispatchers,
)


login_url = settings.login_url
redirect_to_verification = {
    EmployeeStatus.verifier
}


async def check_calendar_access(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    auth_token: Optional[str] = Cookie(None),
    company_info_token: Optional[str] = Cookie(None),
) -> JwtData:
    user_data, comp_data = check_jwt_data(
        auth_token, company_info_token)

    user_data_status = user_data.get("status")

    if user_data_status not in access_calendar:
        active_ids = set(comp_data.get("active_company_ids", []))
        if not active_ids:
            raise ForbiddenError(company_id=company_id)

        first_cid = min(active_ids)
        if user_data_status in redirect_to_verification:
            url = f"/verification/{first_cid}"
        else:
            url = login_url

        raise RedirectHttpException(redirect_to_url=url)

    employee_data = build_jwt_data(user_data, comp_data)

    validate_company_access(
        company_id, employee_data, "calendar", active=False)

    return employee_data


async def check_active_access_calendar(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
):
    validate_company_access(
        company_id, employee_data, "calendar", active=True)
    return employee_data


async def dispatcher2_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
):
    if employee_data.status == dispatcher2:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def dispatchers_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(check_calendar_access),
):
    if employee_data.status in dispatchers:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def active_dispatcher2_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_calendar),
):
    if employee_data.status == dispatcher2:
        raise ForbiddenError(company_id=company_id)
    return employee_data


async def active_dispatchers_exception(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_active_access_calendar),
):
    if employee_data.status in dispatchers:
        raise ForbiddenError(company_id=company_id)
    return employee_data
