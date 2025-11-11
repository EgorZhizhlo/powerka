from pydantic import BaseModel, field_validator, Field, ConfigDict
from typing import Optional, List
from datetime import date as date_

from core.utils.time_utils import date_utc_now
from models.enums import (
    VerificationLegalEntity, OrderWaterType
)


class OrderFilter(BaseModel):
    date: date_ = Field(default_factory=date_utc_now)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=30)

    @field_validator('limit')
    def validator_limit(cls, values):
        if values not in {30, 50, 100}:
            raise ValueError(
                'Некорректное колличества записей на странице')
        return values


class CitySchema(BaseModel):
    id: int
    name: str
    is_deleted: Optional[bool]

    model_config = ConfigDict(from_attributes=True)


class LowOrderItemResponse(BaseModel):
    id: int
    address: str
    client_full_name: str
    phone_number: Optional[str]
    city: CitySchema

    counter_assignment_id: int

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponse(LowOrderItemResponse):
    dispatcher: str
    date: date_
    sec_phone_number: Optional[str]
    legal_entity: VerificationLegalEntity
    counter_number: int
    water_type: OrderWaterType
    price: float
    additional_info: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class OrderListResponse(BaseModel):
    total_count: int
    total_pages: int
    page: int
    limit: int
    orders: List[LowOrderItemResponse]


class CounterAssignmentCreateRequest(BaseModel):
    order_id: int


class CounterAssignmentResponse(BaseModel):
    id: int
    order_id: int
    counter_limit: int
    employee_id: int

    model_config = ConfigDict(from_attributes=True)
