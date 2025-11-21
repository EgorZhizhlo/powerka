from fastapi import status as status_codes

from core.exceptions.base import ApiHttpException


class BadRequestError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class ForbiddenError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class NotFoundError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class ConflictError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
        )


class BadGatewayError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )
