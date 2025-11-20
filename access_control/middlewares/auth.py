from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from itsdangerous import URLSafeTimedSerializer, URLSafeSerializer

from sqlalchemy import select
from models import EmployeeModel, CompanyModel

from access_control.tokens import (
    verify_token,
    verify_untimed_token,
    get_jwt_token_version
)

from core.config import settings
from core.exceptions.app.auth.token import (
    InvalidTokenError, TokenExpiredError
)

from infrastructure.db.session import async_session_maker

SECRET_KEY = settings.secret_key
SALT = settings.salt
TOKEN_EXPIRATION = settings.jwt_token_expiration


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Пути, где токены не нужны
        public_paths = {"/login", "/logout", "/static", "/favicon.ico", "/apple-touch-icon.png"}

        # если запрос идёт на публичный URL → пропускаем сразу
        for prefix in public_paths:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        auth_token = request.cookies.get("auth_token")
        comp_token = request.cookies.get("company_info_token")
        refreshed_cookies: dict[str, str] = {}

        # Валидация токенов и проверка совпадения user_id в токенах
        user_data = None
        comp_data = None

        if auth_token:
            try:
                user_data = verify_token(auth_token)
            except (TokenExpiredError, InvalidTokenError):
                return await self._clear_and_continue(request, call_next)

        if comp_token:
            try:
                comp_data = verify_untimed_token(comp_token)
            except InvalidTokenError:
                return await self._clear_and_continue(request, call_next)

        if not user_data or not comp_data:
            return await self._clear_and_continue(request, call_next)

        u_user_id = user_data.get("id")
        c_user_id = comp_data.get("id")

        if user_data and comp_data and u_user_id != c_user_id:
            return await self._clear_and_continue(request, call_next)

        # Переподписываем auth_token, если версия устарела
        if user_data:
            user_id = u_user_id
            token_ver = user_data.get("ver", 0)
            current_ver = await get_jwt_token_version(
                f"user:{user_id}:auth_version")

            if token_ver != current_ver:
                async with async_session_maker() as session:
                    stmt = (
                        select(EmployeeModel)
                        .where(
                            EmployeeModel.id == user_id,
                            EmployeeModel.is_active.is_(True)
                        )
                    )
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()

                if not user:
                    return await self._clear_and_continue(request, call_next)

                # Переподписываем токен, сохраняя текущую версию
                serializer = URLSafeTimedSerializer(SECRET_KEY)
                refreshed_cookies["auth_token"] = serializer.dumps(
                    {
                        "id": user.id,
                        "last_name": user.last_name,
                        "name": user.name,
                        "patronymic": user.patronymic,
                        "username": user.username,
                        "status": user.status,
                        "ver": current_ver,
                    },
                    salt=SALT
                )

        # Переподписываем company_info_token, если версия устарела
        if comp_data:
            user_id = u_user_id
            token_ver = comp_data.get("ver", 0)
            current_ver = await get_jwt_token_version(
                f"user:{user_id}:company_version")

            if token_ver != current_ver:
                # Обновляем список компаний из БД
                async with async_session_maker() as session:
                    stmt = (
                        select(
                            CompanyModel.id,
                            CompanyModel.is_active
                        ).where(
                            CompanyModel.employees.any(
                                EmployeeModel.id == user_id
                            )
                        )
                        .order_by(CompanyModel.id)
                    )
                    result = await session.execute(stmt)
                    rows = result.all()

                serializer = URLSafeSerializer(
                    SECRET_KEY, salt=SALT)
                payload = {
                    "id": user_id,
                    "all_company_ids": [
                        company_id
                        for company_id, _ in rows
                    ],
                    "active_company_ids": [
                        company_id
                        for company_id, is_active in rows if is_active
                    ],
                    "ver": current_ver,
                }
                refreshed_cookies[
                    "company_info_token"] = serializer.dumps(payload)

        # Пропускаем запрос дальше
        response = await call_next(request)

        # Ставим обновлённые куки
        for name, val in refreshed_cookies.items():
            response.set_cookie(
                key=name,
                value=val,
                max_age=TOKEN_EXPIRATION,
                httponly=True,
                samesite="lax",
                path="/",
            )

        return response

    async def _clear_and_continue(self, request: Request, call_next):
        resp = await call_next(request)
        for name in ("auth_token", "company_info_token"):
            resp.delete_cookie(name, path="/")
        return resp
