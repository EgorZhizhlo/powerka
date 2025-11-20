from fastapi import status as status_codes

from core.exceptions.base import AppHttpException


class UnauthorizedError(AppHttpException):
    def __init__(
        self,
        detail: str = "Ошибка авторизации. Пожалуйста, войдите в систему.",
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_401_UNAUTHORIZED,
            detail=detail,
            company_id=company_id
        )


class ForbiddenError(AppHttpException):
    def __init__(
        self,
        detail: str = "У вас нет доступа к этому разделу.",
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_403_FORBIDDEN,
            detail=detail,
            company_id=company_id
        )


class NotFoundError(AppHttpException):
    def __init__(
        self,
        detail: str,
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail=detail,
            company_id=company_id
        )
