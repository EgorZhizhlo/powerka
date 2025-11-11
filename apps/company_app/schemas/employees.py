from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator
import base64


class EmployeeCreate(BaseModel):
    image: Optional[bytes] = None
    username: str
    email: str
    password: str
    last_name: str
    name: str
    patronymic: str
    status: Optional[str] = ''
    position: str
    is_active: Optional[bool] = True
    default_verifier_id: Optional[int] = None
    default_city_id: Optional[int] = None
    series_id: Optional[int] = None
    city_ids: List[Optional[int]] = []
    route_ids: List[Optional[int]] = []
    trust_verifier: Optional[bool]
    trust_equipment: Optional[bool]

    @field_validator('image', mode='before')
    @classmethod
    def validate_and_decode_image(cls, v):
        if not v:
            return None

        if isinstance(v, bytes):
            return v

        if isinstance(v, str):
            if v.startswith('data:'):
                try:
                    v = v.split(',', 1)[1]
                except IndexError:
                    raise ValueError(
                        "Неверный формат изображения: ожидается 'data:image/...;base64,<данные>'"
                    )
            try:
                decoded = base64.b64decode(v)
                return decoded
            except Exception as e:
                raise ValueError(
                    f"Ошибка декодирования base64 изображения: {str(e)}"
                )
        raise ValueError(
            f"Поле image должно быть строкой base64, bytes или None. "
            f"Получен тип: {type(v).__name__}"
        )


class EmployeeOut(BaseModel):
    id: int
    last_name: str
    name: str
    patronymic: str
    email: str
    status: str
    position: Optional[str] = ''
    is_active: bool
    is_deleted: bool = False
    has_image: bool = False

    trust_verifier: Optional[bool] = None
    trust_equipment: Optional[bool] = None

    default_verifier_fullname: Optional[str] = None
    default_city_name: Optional[str] = None
    series_name: Optional[str] = None

    last_login_strftime_full: str = ""
    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class EmployeesPage(BaseModel):
    items: List[EmployeeOut]
    page: int
    total_pages: int
