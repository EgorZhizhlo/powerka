from fastapi import status as status_codes

from core.exceptions.base import ApiHttpException


class TariffNotFoundError(ApiHttpException):
    def __init__(
        self,
        detail: str = (
            "У компании нет активного тарифного плана. "
            "Обратитесь к администратору для назначения тарифа."
        ),
    ):
        super().__init__(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class TariffForbiddenError(ApiHttpException):
    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=status_codes.HTTP_403_FORBIDDEN,
            detail=detail,
        )
