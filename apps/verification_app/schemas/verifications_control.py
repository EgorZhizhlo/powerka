from datetime import date as date_
from dateutil.relativedelta import relativedelta
from pydantic import (
    BaseModel, ConfigDict, Field, field_validator, model_validator
)
from typing import Optional, List

from core.config import settings
from core.templates.jinja_filters import get_current_date_in_tz

from models.enums import (
    VerificationLegalEntity, VerificationSeal, VerificationWaterType
)


class CreateVerificationEntryForm(BaseModel):
    verification_date: date_ = Field(...)
    interval: int = Field(..., ge=1, le=15)
    end_verification_date: date_ = Field(...)

    seal: VerificationSeal = Field(...)
    legal_entity: VerificationLegalEntity = Field(...)
    water_type: VerificationWaterType = Field(...)

    registry_number_id: int = Field(..., ge=1, le=settings.max_int)
    modification_id: int = Field(..., ge=1, le=settings.max_int)
    series_id: int = Field(..., ge=1, le=settings.max_int)
    location_id: int = Field(..., ge=1, le=settings.max_int)
    city_id: int = Field(..., ge=1, le=settings.max_int)
    method_id: int = Field(..., ge=1, le=settings.max_int)
    reason_id: int | None = Field(None)

    manufacture_year: int = Field(..., ge=1900, le=2100)
    act_number: int = Field(..., ge=0, le=settings.max_int)
    factory_number: str = Field(..., max_length=60)
    meter_info: int = Field(..., ge=0, le=settings.max_int)
    address: str = Field(..., max_length=255)
    client_full_name: str = Field(..., max_length=150)
    client_phone: str = Field(..., max_length=18)
    verification_result: bool = Field(...)

    additional_checkbox_1: bool = False
    additional_checkbox_2: bool = False
    additional_checkbox_3: bool = False
    additional_checkbox_4: bool = False
    additional_checkbox_5: bool = False
    additional_input_1: str = Field("", max_length=100)
    additional_input_2: str = Field("", max_length=100)
    additional_input_3: str = Field("", max_length=100)
    additional_input_4: str = Field("", max_length=100)
    additional_input_5: str = Field("", max_length=100)

    company_tz: str = Field(default="Europe/Moscow", max_length=50)

    deleted_images_id: List[int] = Field(default_factory=list)

    @field_validator("deleted_images_id", mode="before")
    def clean_deleted_images_id(cls, v):
        if not v:
            return []
        return [int(i) for i in v if str(i).strip().isdigit()]

    @model_validator(mode="after")
    def validate_verification_period(self):
        current_date = get_current_date_in_tz(self.company_tz)
        if self.verification_date > current_date:
            raise ValueError("Дата поверки не может быть позже текущей даты.")

        expected_end = self.verification_date + relativedelta(
            years=self.interval
        )
        if (expected_end - self.end_verification_date).days != 1:
            raise ValueError(
                "Дата поверки и дата окончания поверки не соблюдают "
                f"интервал {self.interval} год(а)/лет."
            )

        return self

    @model_validator(mode="after")
    def validate_logical_dependencies(self):
        if not self.verification_result and not self.reason_id:
            raise ValueError(
                "Необходимо указать причину при отрицательном "
                "результате поверки."
            )
        return self


class UpdateVerificationEntryForm(CreateVerificationEntryForm):
    verifier_id: int = Field(..., ge=1, le=settings.max_int)


class MetrologInfoForm(BaseModel):
    qh: Optional[float] = Field(None, ge=0.6, le=1.5)
    before_water_temperature: Optional[float] = Field(None, ge=0, le=100)
    before_air_temperature: Optional[float] = Field(None, ge=-50, le=50)
    before_humdity: Optional[float] = Field(None, ge=0, le=100)
    before_pressure: Optional[float] = Field(None, ge=0, le=2000)
    after_water_temperature: Optional[float] = Field(None, ge=0, le=100)
    after_air_temperature: Optional[float] = Field(None, ge=-50, le=50)
    after_humdity: Optional[float] = Field(None, ge=0, le=100)
    after_pressure: Optional[float] = Field(None, ge=0, le=2000)

    high_error_rate: bool = False
    use_opt: bool = False

    first_meter_water_according_qmin: Optional[float] = None
    second_meter_water_according_qmin: Optional[float] = None
    third_meter_water_according_qmin: Optional[float] = None
    first_reference_water_according_qmin: Optional[float] = None
    second_reference_water_according_qmin: Optional[float] = None
    third_reference_water_according_qmin: Optional[float] = None

    first_meter_water_according_qp: Optional[float] = None
    second_meter_water_according_qp: Optional[float] = None
    third_meter_water_according_qp: Optional[float] = None
    first_reference_water_according_qp: Optional[float] = None
    second_reference_water_according_qp: Optional[float] = None
    third_reference_water_according_qp: Optional[float] = None

    first_meter_water_according_qmax: Optional[float] = None
    second_meter_water_according_qmax: Optional[float] = None
    third_meter_water_according_qmax: Optional[float] = None
    first_reference_water_according_qmax: Optional[float] = None
    second_reference_water_according_qmax: Optional[float] = None
    third_reference_water_according_qmax: Optional[float] = None

    first_water_count_qmin: Optional[float] = None
    second_water_count_qmin: Optional[float] = None
    third_water_count_qmin: Optional[float] = None
    first_water_count_qp: Optional[float] = None
    second_water_count_qp: Optional[float] = None
    third_water_count_qp: Optional[float] = None
    first_water_count_qmax: Optional[float] = None
    second_water_count_qmax: Optional[float] = None
    third_water_count_qmax: Optional[float] = None


class VerificationEntryFilter(BaseModel):
    page: Optional[int] = Field(1, ge=1)
    limit: Optional[int] = Field(30, ge=30)
    date_from: Optional[date_] = None
    date_to: Optional[date_] = None
    client_address: Optional[str] = None
    factory_number: Optional[str] = None
    series_id: Optional[int] = None
    client_phone: Optional[str] = None
    city_id: Optional[int] = None
    employee_id: Optional[int] = None
    water_type: Optional[VerificationWaterType] = None
    act_number: Optional[int] = None

    @model_validator(mode="after")
    def validate_verification_period(self):
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                raise ValueError(
                    '"Дата с" должна быть меньше или равна "Дата по"'
                )
        return self

    @field_validator('limit')
    def validator_limit(cls, values):
        if values not in {30, 50, 100}:
            raise ValueError(
                'Некорректное колличества записей на странице')
        return values


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_name: Optional[str] = None
    name: Optional[str] = None
    patronymic: Optional[str] = None


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ActNumberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    act_number: Optional[int] = None
    address: Optional[str] = None
    client_full_name: Optional[str] = None


class RegistryNumberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    si_type: Optional[str] = None
    registry_number: Optional[str] = None


class ModificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    modification_name: Optional[str] = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None


class MetrologOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int


class VerificationEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    verification_date: Optional[date_] = None
    factory_number: Optional[str] = None
    meter_info: Optional[int] = None
    end_verification_date: Optional[date_] = None
    verification_result: Optional[bool] = None
    water_type: Optional[VerificationWaterType] = None
    seal: Optional[VerificationSeal] = None
    manufacture_year: Optional[int] = None

    employee: Optional[EmployeeOut] = None
    act_number: Optional[ActNumberOut] = None
    registry_number: Optional[RegistryNumberOut] = None
    modification: Optional[ModificationOut] = None
    location: Optional[LocationOut] = None
    series: Optional[SeriesOut] = None
    metrolog: Optional[MetrologOut] = None
    city: Optional[CityOut] = None

    created_at_formatted: Optional[str] = None
    updated_at_formatted: Optional[str] = None


class VerificationEntryListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: List[VerificationEntryOut]
    page: int
    limit: int
    total_pages: Optional[int] = None
    total_entries: Optional[int] = None

    verified_entry: Optional[int] = 0
    not_verified_entry: Optional[int] = 0

    @field_validator('limit')
    def validator_limit(cls, values):
        if values not in {30, 50, 100}:
            raise ValueError(
                'Некорректное колличества записей на странице')
        return values
