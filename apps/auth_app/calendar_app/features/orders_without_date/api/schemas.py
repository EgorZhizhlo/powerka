from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime as datetime_

from models.enums import OrderStatus


class RouteSchema(BaseModel):
    id: Optional[int]
    name: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class CitySchema(BaseModel):
    id: Optional[int]
    name: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class OrderSchema(BaseModel):
    id: Optional[int]
    address: Optional[str]
    city: CitySchema
    phone_number: Optional[str]
    client_full_name: Optional[str]
    additional_info: Optional[str]
    date_of_get: Optional[datetime_]
    status: Optional[OrderStatus]

    model_config = ConfigDict(from_attributes=True)


class OrdersPaginated(BaseModel):
    total: int = 0
    page: int
    page_size: int
    total_pages: int = 0
    items: List[OrderSchema] = []


class OrderListParams(BaseModel):
    company_id: int = Field(...)
    route_id: Optional[int] = Field(None)
    status: Optional[OrderStatus] = Field(None)
    page: int = Field(1, ge=1)
    page_size: int = Field(30, ge=1, le=100)

    model_config = ConfigDict(populate_by_name=True)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus = Field(...)

    model_config = ConfigDict(from_attributes=True)
