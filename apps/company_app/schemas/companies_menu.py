from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class EditCompanyFormDirector(BaseModel):
    name: str = Field(..., max_length=200)
    email: str = Field(..., max_length=120)
    inn: str = Field(..., max_length=12)
    address: str = Field(..., max_length=150)
    workplace: str = Field(..., max_length=120)
    accreditation_certificat: str = Field(..., max_length=30)
    organization_code: str = Field(..., max_length=30)
    contact_responsible_person: str = Field(..., max_length=200)
    additional: Optional[str] = Field("", max_length=200)

    daily_verifier_verif_limit: Optional[int] = Field(None)
    longitude: Optional[float] = Field(0, ge=-180, le=180)
    latitude: Optional[float] = Field(0, ge=-90, le=90)
    default_pressure: Optional[int] = Field(0, ge=-1500, le=1500)
    timezone: Optional[str] = Field("Europe/Moscow", max_length=50)

    additional_checkbox_1: Optional[str] = Field("")
    additional_checkbox_2: Optional[str] = Field("")
    additional_checkbox_3: Optional[str] = Field("")
    additional_checkbox_4: Optional[str] = Field("")
    additional_checkbox_5: Optional[str] = Field("")

    additional_input_1: Optional[str] = Field("", max_length=100)
    additional_input_2: Optional[str] = Field("", max_length=100)
    additional_input_3: Optional[str] = Field("", max_length=100)
    additional_input_4: Optional[str] = Field("", max_length=100)
    additional_input_5: Optional[str] = Field("", max_length=100)

    customer_field: Optional[bool] = Field(False)
    customer_field_required: Optional[bool] = Field(False)
    legal_entity: Optional[bool] = Field(False)
    price_field: Optional[bool] = Field(False)
    price_field_required: Optional[bool] = Field(False)
    water_field: Optional[bool] = Field(False)
    water_field_required: Optional[bool] = Field(False)

    yandex_disk_token: Optional[str] = Field("")

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> str:
        """Проверяет, что переданная timezone валидна"""
        if not v:
            return "Europe/Moscow"

        # Проверяем валидность timezone
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Недопустимая временная зона: {v}")

        return v


class EditCompanyFormAdmin(EditCompanyFormDirector):
    employee_ids: List[int] = Field(default_factory=list)
