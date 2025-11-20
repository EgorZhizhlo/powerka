from access_control.tokens.jwt_data import JwtData
from access_control.roles.definitions import (
    access_company_no_admin,
    access_calendar_no_admin,
    access_verification_no_admin,
)

from core.exceptions.app.common import (
    UnauthorizedError, ForbiddenError
)

from models.enums import EmployeeStatus


def validate_company_access(
    company_id: int,
    employee_data: JwtData,
    section: str,
    active: bool = False
):
    map_section = {
        "company": access_company_no_admin,
        "verification": access_verification_no_admin,
        "calendar": access_calendar_no_admin,
    }
    if active:
        if employee_data.status in map_section.get(section, set()):
            if company_id not in employee_data.active_company_ids:
                raise UnauthorizedError(company_id=company_id)
        return

    if employee_data.status == EmployeeStatus.director:
        if company_id not in employee_data.all_company_ids:
            raise ForbiddenError(company_id=company_id)
    elif employee_data.status == EmployeeStatus.auditor:
        if company_id not in employee_data.active_company_ids:
            raise ForbiddenError(company_id=company_id)
