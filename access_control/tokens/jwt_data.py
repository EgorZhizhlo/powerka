from typing import Optional, Tuple
from pydantic import BaseModel, ConfigDict

from core.config import settings
from core.exceptions.base import RedirectHttpException
from core.exceptions.app.auth.token import (
    InvalidTokenError, TokenExpiredError
)

from access_control.tokens.jwt_control import (
    verify_token, verify_untimed_token
)


class JwtData(BaseModel):
    id: int
    status: str
    name: str
    last_name: str
    patronymic: str
    username: str
    all_company_ids: set[int]
    active_company_ids: set[int]
    model_config = ConfigDict(from_attributes=True)


def build_jwt_data(
        user_data: dict, comp_data: dict) -> JwtData:
    return JwtData(
        **user_data,
        all_company_ids=set(comp_data.get("all_company_ids", []) or []),
        active_company_ids=set(comp_data.get("active_company_ids", []) or []),
    )


def check_jwt_data(
        auth_token: Optional[str],
        company_info_token: Optional[str],
) -> Tuple[dict, dict]:
    if not auth_token or not company_info_token:
        raise RedirectHttpException(redirect_to_url=settings.logout_url)

    try:
        user_data = verify_token(auth_token)
        company_data = verify_untimed_token(company_info_token)
    except (TokenExpiredError, InvalidTokenError):
        raise RedirectHttpException(redirect_to_url=settings.logout_url)

    user_id = user_data.get("id")
    comp_id = company_data.get("id")
    user_status = user_data.get("status")

    if user_id and comp_id and user_id != comp_id:
        raise RedirectHttpException(redirect_to_url=settings.logout_url)

    from access_control.roles.definitions import employee_status

    if user_status not in employee_status:
        raise RedirectHttpException(redirect_to_url=settings.logout_url)

    return user_data, company_data
