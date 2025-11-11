from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import date as date_

from models.enums import OrderWaterType, VerificationLegalEntity


class RouteSchema(BaseModel):
    id: int
    name: str
    day_limit: int
    color: str
    busy: Optional[int] = None
    is_deleted: Optional[bool]

    model_config = ConfigDict(from_attributes=True)


class RouteCalendarSchema(BaseModel):
    id: int
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class CitySchema(BaseModel):
    id: int
    name: str
    is_deleted: Optional[bool]

    model_config = ConfigDict(from_attributes=True)


class EmployeeSchema(BaseModel):
    id: int
    last_name: str
    name: str
    patronymic: str

    model_config = ConfigDict(from_attributes=True)


class LowOrderSchema(BaseModel):
    id: int
    client_full_name: Optional[str] = None
    address: str
    date: Optional[date_] = None
    weight: Optional[int]
    phone_number: str

    model_config = ConfigDict(from_attributes=True)


class OrderSchema(LowOrderSchema):
    route: Optional[RouteSchema] = None
    city: CitySchema

    sec_phone_number: Optional[str] = None
    legal_entity: Optional[VerificationLegalEntity] = VerificationLegalEntity.individual
    counter_number: int = Field(..., ge=0, le=10)
    water_type: Optional[OrderWaterType] = OrderWaterType.unnamed
    price: Optional[float] = None
    additional_info: Optional[str] = None
    weight: Optional[int]
    no_date: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class RouteOrdersSchema(BaseModel):
    route_id: Optional[int] = None
    route_name: str
    route_color: str
    employee: Optional[EmployeeSchema] = None
    orders: List[LowOrderSchema]

    model_config = ConfigDict(from_attributes=True)


class CalendarBaseModel(BaseModel):
    title: str


class CalendarOrdersResponse(CalendarBaseModel):
    orders: List[RouteOrdersSchema]

    model_config = ConfigDict(from_attributes=True)


class CalendarOrderDetailResponse(CalendarBaseModel):
    order: OrderSchema

    model_config = ConfigDict(from_attributes=True)


class OrderCreateForm(BaseModel):
    route_id: Optional[int] = None
    city_id: Optional[int]
    address: str
    client_full_name: Optional[str] = None
    phone_number: str
    sec_phone_number: Optional[str] = None
    legal_entity: Optional[VerificationLegalEntity] = VerificationLegalEntity.individual
    counter_number: int = Field(..., ge=0, le=10)
    water_type: Optional[OrderWaterType] = OrderWaterType.unnamed
    price: Optional[float] = None
    additional_info: Optional[str] = None
    date: Optional[date_] = None
    weight: Optional[int] = None
    no_date: Optional[bool] = False

    model_config = ConfigDict(from_attributes=False)


class OrderUpdateForm(BaseModel):
    route_id: Optional[int] = None
    city_id: Optional[int] = None
    address: Optional[str] = None
    client_full_name: Optional[str] = None
    phone_number: Optional[str] = None
    sec_phone_number: Optional[str] = None
    legal_entity: Optional[VerificationLegalEntity] = VerificationLegalEntity.individual
    counter_number: int = Field(..., ge=0, le=10)
    water_type: Optional[OrderWaterType] = OrderWaterType.unnamed
    price: Optional[float] = None
    additional_info: Optional[str] = None
    weight: Optional[int] = None
    date: Optional[date_] = None
    no_date: Optional[bool] = None

    model_config = ConfigDict(from_attributes=False)


class ReweightOrderRequest(BaseModel):
    ordered_ids: List[int]
