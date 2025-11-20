from typing import Optional
from fastapi import Cookie

from core.exceptions.app.common import ForbiddenError

from access_control.tokens import (
    JwtData,
    build_jwt_data,
    check_jwt_data
)
from access_control.roles import (
    access_tarif
)


async def check_tariff_access(
    auth_token: Optional[str] = Cookie(None),
    company_info_token: Optional[str] = Cookie(None),
) -> JwtData:
    """Проверка доступа к управлению тарифами"""
    user_data, comp_data = check_jwt_data(
        auth_token, company_info_token
    )

    user_data_status = user_data.get("status")

    if user_data_status not in access_tarif:
        raise ForbiddenError(
            detail=(
                "Доступ к управлению тарифами "
                "разрешен только администраторам"
            )
        )

    employee_data = build_jwt_data(user_data, comp_data)

    return employee_data
