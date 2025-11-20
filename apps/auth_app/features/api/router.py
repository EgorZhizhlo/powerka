from fastapi import APIRouter, HTTPException, Depends, Cookie
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.security import check_password_hash

from access_control.tokens import (
    verify_token, verify_untimed_token,
    get_jwt_token_version,
    create_token, create_untimed_token,
)
from access_control.roles import (
    access_company
)

from infrastructure.db import async_db_session

from apps.auth_app.repositories import EmployeeRepository, CompanyRepository
from apps.auth_app.schemas.auth import LoginRequestSchema

from core.config import settings
from core.exceptions.app.common import (
    UnauthorizedError
)


auth_api_router = APIRouter(prefix="/auth/api")


@auth_api_router.post("/login")
async def login_user(
    login_request: LoginRequestSchema = Depends(),
    session: AsyncSession = Depends(async_db_session),
):
    emp_repo = EmployeeRepository(session)
    user = await emp_repo.get_active_by_username(login_request.username)
    if not user or not check_password_hash(
        user.password, login_request.password
    ):
        raise UnauthorizedError

    await emp_repo.update_login_date(user.id)

    auth_token = await create_token(
        {
            "id": user.id,
            "last_name": user.last_name,
            "name": user.name,
            "patronymic": user.patronymic,
            "username": login_request.username,
            "status": user.status,
        }
    )

    company_repo = CompanyRepository(session)

    all_ids, active_ids = await company_repo.get_companies_info_for_token(
        user.id)
    companies_dir = {
        "id": user.id,
        "all_company_ids": all_ids,
        "active_company_ids": active_ids,
    }

    company_info_token = await create_untimed_token(companies_dir)

    status = user.status
    if status in access_company:
        redirect_url = settings.url_path_map[status]
    else:
        if not all_ids:
            raise HTTPException(
                status_code=404,
                detail="Вам не назначена компания!"
            )
        redirect_url = f"{settings.url_path_map[status]}?company_id={min(all_ids)}"

    cookie_params = dict(
        max_age=settings.jwt_token_expiration,
        httponly=True,
        samesite="lax",
        path="/",
    )

    resp = JSONResponse({"redirect": redirect_url})
    resp.set_cookie("auth_token", auth_token, **cookie_params)
    resp.set_cookie("company_info_token", company_info_token, **cookie_params)
    return resp


@auth_api_router.get("/vers")
async def get_versions(
    auth_token: str = Cookie(None),
    company_info_token: str = Cookie(None),
):
    """
    Получить текущие версии токенов пользователя (auth и company).
    """
    if not auth_token:
        raise HTTPException(
            status_code=401,
            detail="Нет токена"
        )

    try:
        user_data = verify_token(auth_token)
        company_data = verify_untimed_token(company_info_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Невалидный токен"
        )

    user_id = user_data.get("id")

    auth_ver = await get_jwt_token_version(f"user:{user_id}:auth_version")
    company_ver = await get_jwt_token_version(f"user:{user_id}:company_version")

    return JSONResponse({
        "user_id": user_id,
        "auth_version": auth_ver,
        "company_version": company_ver,
        "auth_ver": user_data.get("ver"),
        "company_ver": company_data.get("ver"),
        "active": company_data.get("active_company_ids"),
        "all": company_data.get("all_company_ids")
    })
