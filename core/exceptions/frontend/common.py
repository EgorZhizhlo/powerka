from fastapi import status as status_codes

from core.exceptions.base import FrontendHttpException


class BadRequestError(FrontendHttpException):
    def __init__(
        self,
        detail: str,
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=detail,
            company_id=company_id
        )


class ForbiddenError(FrontendHttpException):
    def __init__(
        self,
        detail: str,
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_403_FORBIDDEN,
            detail=detail,
            company_id=company_id
        )


class NotFoundError(FrontendHttpException):
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


class ConflictError(FrontendHttpException):
    def __init__(
        self,
        detail: str,
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )


class InternalServerError(FrontendHttpException):
    def __init__(
        self,
        detail: str = (
            "Внутренняя ошибка сервера. "
            "Пожалуйста, попробуйте позже."
        ),
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            company_id=company_id
        )
