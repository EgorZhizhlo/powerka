from fastapi import status as status_codes

from core.exceptions.base import AppHttpException


class TokenExpiredError(AppHttpException):
    def __init__(
            self,
            detail: str = "Ваша сессия истекла. Пожалуйста, войдите в систему снова.",
            company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=detail,
            company_id=company_id
        )


class InvalidTokenError(AppHttpException):
    def __init__(
            self,
            detail: str = "Ошибка авторизации. Пожалуйста, войдите в систему.",
            company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=detail,
            company_id=company_id
        )
