from fastapi import HTTPException, status as status_codes


class BaseHttpException(HTTPException):
    exception_type = "base"

    def __init__(
        self,
        status_code: int,
        detail: str | None = None,
        *,
        company_id: int | None = None,
        redirect_url: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)

        # общие поля, которые будут у ВСЕХ ошибок
        self.company_id = company_id
        self.redirect_url = redirect_url


class ApiHttpException(BaseHttpException):
    pass


class FrontendHttpException(BaseHttpException):
    pass


class AppHttpException(BaseHttpException):
    pass


class RedirectHttpException(BaseHttpException):
    def __init__(self, redirect_to_url: str):
        super().__init__(
            status_code=status_codes.HTTP_303_SEE_OTHER,
            redirect_url=redirect_to_url
        )
