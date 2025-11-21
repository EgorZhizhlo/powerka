from fastapi import status as status_codes

from core.exceptions.base import FrontendHttpException


class FrontendVerificationVerifierError(FrontendHttpException):
    def __init__(
        self,
        company_id: int = None,
        detail: str = (
            "У записи поверки не указан поверитель.\n"
            "Проверьте, что за записью закреплён поверитель."
        ),
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )


class FrontendVerificationEquipmentError(FrontendHttpException):
    def __init__(
        self,
        company_id: int = None,
        detail: str = (
            "За записью поверки не закреплено оборудование.\n"
            "Проверьте, что хотя бы одно средство измерения "
            "привязано к данной поверке."
        ),
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )


class FrontendVerificationEquipmentExpiredError(FrontendHttpException):
    def __init__(
            self,
            equipments: list[str],
            company_id: int = None,
    ):
        formatted_list = "\n• " + "\n• ".join(equipments)
        detail = (
            "У одного или нескольких средств измерений, "
            "закреплённых за записью поверки, истёк срок поверки.\n"
            "Необходимо провести поверку следующего оборудования:"
            f"{formatted_list}"
        )
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )


class FrontendVerifProtocolAccessError(FrontendHttpException):
    def __init__(
        self,
        detail: str = (
            "Невозможно сформировать протокол поверки.\n"
            "Проверьте:\n"
            " • Cуществует ли запись поверки, для которой "
            "вы хотите получить протокол;\n"
            " • Cуществуют ли метрологические характеристики, "
            "связанные с этой поверкой;\n"
            " • Eсть ли у вас права доступа для просмотра этого протокола;\n"
            " • Не была ли запись удалена;\n"
        ),
        company_id: int = None,
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )


class FrontendCreateVerifDefaultVerifierError(FrontendHttpException):
    def __init__(
        self,
        detail: str = (
            "Создание записи поверки невозможно. "
            "Для Вас не назначен поверитель по-умолчанию."
        ),
        company_id: int = None
    ):
        super().__init__(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=detail,
            company_id=company_id
        )
