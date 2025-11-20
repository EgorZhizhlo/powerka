from typing import List, Optional
from fastapi import Request, Depends, Cookie, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from core.config import settings
from core.exceptions.base import RedirectHttpException
from core.exceptions.app.common import ForbiddenError

from models import EmployeeModel
from models.enums import EmployeeStatus

from infrastructure.db.session import async_db_session

from access_control.tokens import (
    JwtData,
    build_jwt_data,
    check_jwt_data
)
from access_control.roles import (
    validate_company_access,

    no_access_company
)


login_url = settings.login_url
redirect_to_calendar = {
    EmployeeStatus.dispatcher1,
    EmployeeStatus.dispatcher2
}
redirect_to_verification = {
    EmployeeStatus.verifier
}


def _redirect_non_access_roles(
        user_data_status: str, active_company_ids: List[int]
) -> None:
    if user_data_status not in no_access_company:
        return

    active_ids = set(active_company_ids)
    if not active_ids:
        raise ForbiddenError

    company_id = min(active_ids)

    if user_data_status in redirect_to_calendar:
        url = f"/calendar?company_id={company_id}"
    elif user_data_status in redirect_to_verification:
        url = f"/verification?company_id={company_id}"
    else:
        url = login_url

    raise RedirectHttpException(redirect_to_url=url)


async def check_companies_access(
    request: Request,
    auth_token: Optional[str] = Cookie(None),
    company_info_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(async_db_session)
) -> JwtData:
    user_data, comp_data = check_jwt_data(
        auth_token, company_info_token)

    user_data_status = user_data.get("status")
    active_company_ids = comp_data.get("active_company_ids", [])

    _redirect_non_access_roles(user_data_status, active_company_ids)

    if user_data_status == EmployeeStatus.auditor:
        if request.method.upper() != "GET":
            raise ForbiddenError

        user_data_id = user_data.get("id")

        stmt = await session.execute(
            select(
                EmployeeModel.trust_equipment,
                EmployeeModel.trust_verifier
            )
            .where(EmployeeModel.id == user_data_id)
        )
        trust_equipment, trust_verifier = stmt.one()

        if not (trust_equipment or trust_verifier):
            raise ForbiddenError

    return build_jwt_data(user_data, comp_data)


async def check_company_access(
    request: Request,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    auth_token: Optional[str] = Cookie(None),
    company_info_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(async_db_session)
) -> JwtData:
    user_data, comp_data = check_jwt_data(
        auth_token, company_info_token)

    user_data_status = user_data.get("status")
    active_company_ids = comp_data.get("active_company_ids", [])

    _redirect_non_access_roles(user_data_status, active_company_ids)

    if user_data_status == EmployeeStatus.auditor:
        path = request.url.path.rstrip("/")
        method = request.method.upper()

        user_data_id = user_data.get("id")

        stmt = await session.execute(
            select(
                EmployeeModel.trust_equipment,
                EmployeeModel.trust_verifier
            )
            .where(EmployeeModel.id == user_data_id)
        )
        trust_equipment, trust_verifier = stmt.one()

        allowed = False
        if path == f"{settings.company_url}" and method == "GET":
            allowed = bool(trust_equipment or trust_verifier)

        elif path.startswith(
                f"{settings.company_url}/equipment"
        ) and method in {"GET", "POST", "PUT", "DELETE"}:
            allowed = bool(trust_equipment)

        elif path.startswith(
                f"{settings.company_url}/verifier"
        ) and method in {"GET", "POST", "PUT"}:
            allowed = bool(trust_verifier)

        if not allowed:
            raise ForbiddenError(company_id=company_id)

    return build_jwt_data(user_data, comp_data)


async def check_include_in_active_company(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_company_access),
):
    validate_company_access(company_id, user_data, "company", active=True)
    return user_data


async def check_include_in_not_active_company(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_company_access),
):
    validate_company_access(company_id, user_data, "company", active=False)
    return user_data
