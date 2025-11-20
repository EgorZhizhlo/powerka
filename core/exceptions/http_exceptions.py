from fastapi import HTTPException


class CustomHTTPException(HTTPException):
    def __init__(
            self, status_code: int, detail: str = None,
            company_id: int = None, redirect_url: str = None):
        super().__init__(
            status_code=status_code, detail=detail)
        self.company_id = company_id
        self.redirect_url = redirect_url


class RedirectHttpException(CustomHTTPException):
    def __init__(self, redirect_to_url: str):
        super().__init__(
            status_code=303,
            redirect_url=redirect_to_url
        )


class NotFoundException(CustomHTTPException):
    def __init__(
            self, detail: str = "Запрашиваемый ресурс не найден.",
            company_id: int = None):
        super().__init__(status_code=404, detail=detail, company_id=company_id)


class BadRequestException(CustomHTTPException):
    def __init__(
            self, detail: str = "Запрос был недействительным или не может быть обработан.",
            company_id: int = None):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class BadFormException(CustomHTTPException):
    def __init__(
            self, detail: str = "Не все обязательные поля в форме были заполнены.",
            company_id: int = None):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class BadFormHTTPException(HTTPException):
    def __init__(
            self,
            detail: str = "Не все обязательные поля в форме были заполнены."):
        super().__init__(status_code=400, detail=detail)


class ConflictException(CustomHTTPException):
    def __init__(
            self, detail: str = "Запрос не может быть выполнен из-за конфликта с текущим состоянием ресурса.",
            company_id: int = None):
        super().__init__(status_code=409, detail=detail, company_id=company_id)


class InternalServerErrorException(CustomHTTPException):
    def __init__(
            self, detail: str = "Произошла неожиданная ошибка на сервере.",
            company_id: int = None):
        super().__init__(status_code=500, detail=detail, company_id=company_id)


class ValidationErrorException(BadRequestException):
    def __init__(
            self, detail: str = "Ошибка валидации данных.",
            company_id: int = None):
        super().__init__(detail=detail, company_id=company_id)


class ResourceAlreadyExistsException(ConflictException):
    def __init__(
            self, detail: str = "Ресурс уже существует.",
            company_id: int = None):
        super().__init__(detail=detail, company_id=company_id)


class MethodNotAllowedException(CustomHTTPException):
    def __init__(
            self, detail: str = "Метод не разрешен для данного ресурса.",
            company_id: int = None):
        super().__init__(status_code=405, detail=detail, company_id=company_id)


class CompanyIsNotActive(CustomHTTPException):
    def __init__(
            self, detail: str = "Данная компания является неактивной! Внести изменения не получится. Обратитесь к администрации.",
            company_id: int = None):
        super().__init__(status_code=404, detail=detail, company_id=company_id)


class EmployeeIsNotActive(CustomHTTPException):
    def __init__(
            self, detail: str = "Вы являетесь неактивным сотрудником! Для продолжения обратитесь к администрации.",
            company_id: int = None):
        super().__init__(status_code=404, detail=detail, company_id=company_id)


class VerificationDateBlockException(HTTPException):
    def __init__(
        self,
        detail: str = "Создание или редактирование записи поверки на указанную дату невозможно.",
    ):
        super().__init__(status_code=400, detail=detail)


class CustomVerificationDateBlockException(CustomHTTPException):
    def __init__(
        self,
        detail: str = "Создание или редактирование записи поверки на указанную дату невозможно.",
        company_id: int = None
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class VerificationFactoryNumBlockException(HTTPException):
    def __init__(
        self,
        detail: str = "Запись поверки с таким заводским номером уже существует.",
    ):
        super().__init__(status_code=400, detail=detail)


class VerificationCityIdBlockException(HTTPException):
    def __init__(
        self,
        detail: str = "Выбранный город для записи поверки недоступен.",
    ):
        super().__init__(status_code=400, detail=detail)


class CompanyVerificationLimitException(HTTPException):
    def __init__(
        self,
        detail: str = "Лимит поверок на день в компании не задан или имеет недопустимое значение.",
    ):
        super().__init__(status_code=400, detail=detail)


class CustomCompanyVerificationLimitException(CustomHTTPException):
    def __init__(
        self,
        detail: str = "Лимит поверок на день в компании не задан или имеет недопустимое значение.",
        company_id: int = None
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class VerificationDefaultVerifierException(HTTPException):
    def __init__(
        self,
        detail: str = "У пользователя не задан поверитель по умолчанию.",
    ):
        super().__init__(status_code=400, detail=detail)


class CustomCreateVerifDefaultVerifierException(CustomHTTPException):
    def __init__(
        self,
        detail: str = "Создание записи поверки невозможно. "
        "Для Вас не назначен поверитель по-умолчанию.",
        company_id: int = None
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class VerificationDefaultVerifierEquipmentException(HTTPException):
    def __init__(
        self,
        detail: str = "У поверителя по умолчанию не задано оборудование.",
    ):
        super().__init__(status_code=400, detail=detail)


class CustomVerificationDefaultVerifierEquipmentException(CustomHTTPException):
    def __init__(
        self,
        detail: str = "У поверителя по умолчанию не задано оборудование.",
        company_id: int = None
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class CustomVerificationVerifierException(HTTPException):
    def __init__(
        self,
        detail: str = "В записи поверки отсутствует поверитель.",
        company_id: int = None,
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class CustomVerificationEquipmentException(HTTPException):
    def __init__(
        self,
        detail: str = "В записи поверки отсутствует оборудование.",
        company_id: int = None,
    ):
        super().__init__(status_code=400, detail=detail, company_id=company_id)


class YandexTokenException(HTTPException):
    def __init__(
        self,
        detail: str = "В компании указан недействительный токен Яндекс.Диска.",
    ):
        super().__init__(status_code=400, detail=detail)


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


async def check_is_none(result, type, id, company_id):
    if not result:
        raise NotFoundException(
            detail=f"Запись {type} id:{id} не найдена!",
            company_id=company_id
        )
