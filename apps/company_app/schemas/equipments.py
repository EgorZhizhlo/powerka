from typing import Optional, List
from pydantic import (
    BaseModel, ConfigDict,
    Field, field_validator
)
import base64

from models.enums import EquipmentType
from core.config import settings


class ItemBase(BaseModel):
    name: str = Field(..., max_length=150)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(ItemBase):
    pass


class ItemOut(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class OkResponse(BaseModel):
    ok: bool = True


class EquipmentForm(BaseModel):
    image: Optional[bytes] = Field(None)
    image2: Optional[bytes] = Field(None)
    document_pdf: Optional[bytes] = Field(None)
    name: str = Field(..., max_length=80)
    full_name: str = Field(..., max_length=150)
    factory_number: str = Field(..., max_length=30, pattern=r"^[\w\d\s\-,.]+$")
    inventory_number: int = Field(...)
    type: EquipmentType
    register_number: Optional[str] = Field("", max_length=100)
    list_number: Optional[str] = Field("", max_length=100)
    is_opt: Optional[bool] = Field(False)
    year_of_issue: Optional[int] = Field(None, ge=1901, le=2099)
    measurement_range: Optional[str] = Field("", max_length=255)
    error_or_uncertainty: Optional[str] = Field("", max_length=255)
    software_identifier: Optional[str] = Field("", max_length=255)
    activity_id: Optional[int] = Field(None, ge=1, le=settings.max_int)
    si_type_id: Optional[int] = Field(None, ge=1, le=settings.max_int)
    manufacturer_country: Optional[str] = Field("", max_length=120)
    manufacturer_name: Optional[str] = Field("", max_length=255)
    commissioning_year: Optional[int] = Field(None, ge=1900, le=2100)
    ownership_document: Optional[str] = Field("", max_length=255)
    storage_place: Optional[str] = Field("", max_length=255)

    @field_validator('image', 'image2', mode='before')
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
                        "Неверный формат изображения: "
                        "ожидается 'data:image/...;base64,<данные>'"
                    )
            try:
                return base64.b64decode(v)
            except Exception as e:
                raise ValueError(
                    f"Ошибка декодирования base64 изображения: {str(e)}"
                )
        raise ValueError(
            f"Изображение должно быть строкой base64, bytes или None. "
            f"Получен тип: {type(v).__name__}"
        )

    @field_validator('document_pdf', mode='before')
    @classmethod
    def validate_and_decode_pdf(cls, v):
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
                        "Неверный формат PDF: "
                        "ожидается 'data:application/pdf;base64,<данные>'"
                    )
            try:
                return base64.b64decode(v)
            except Exception as e:
                raise ValueError(
                    f"Ошибка декодирования base64 PDF: {str(e)}"
                )
        raise ValueError(
            f"PDF документ должен быть строкой base64, bytes или None. "
            f"Получен тип: {type(v).__name__}"
        )


class EquipmentOut(BaseModel):
    id: int
    name: str
    full_name: str
    factory_number: str
    inventory_number: int
    type: EquipmentType

    activity_id: Optional[int] = None
    si_type_id: Optional[int] = None

    register_number: Optional[str] = ""
    list_number: Optional[str] = ""
    is_opt: Optional[bool] = False
    is_deleted: bool = False

    image_url: Optional[str] = None
    image2_url: Optional[str] = None
    has_document: bool = False

    year_of_issue: Optional[int] = None
    commissioning_year: Optional[int] = None

    measurement_range: Optional[str] = ""
    error_or_uncertainty: Optional[str] = ""
    software_identifier: Optional[str] = ""

    manufacturer_country: Optional[str] = ""
    manufacturer_name: Optional[str] = ""
    ownership_document: Optional[str] = ""
    storage_place: Optional[str] = ""

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "register_number",
        "list_number",
        "measurement_range",
        "error_or_uncertainty",
        "software_identifier",
        "manufacturer_country",
        "manufacturer_name",
        "ownership_document",
        "storage_place",
        mode="before"
    )
    def none_to_empty(cls, v):
        return v or ""


class EquipmentsPage(BaseModel):
    items: List[EquipmentOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
