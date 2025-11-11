from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date as date_

from models.enums import OrderWaterType, VerificationLegalEntity


class RouteSchema(BaseModel):
    id: int
    name: str
    day_limit: int
    color: str
    busy: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CitySchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class EmployeeSchema(BaseModel):
    id: int
    last_name: str
    name: str
    patronymic: str
    has_assignment: bool

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
    counter_number: int
    water_type: Optional[OrderWaterType] = OrderWaterType.unnamed
    price: Optional[float] = None
    additional_info: Optional[str] = None
    weight: Optional[int]
    no_date: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class OrderingRouteSchema(RouteSchema):
    assigned_employee_id: Optional[int] = None
    orders: List[OrderSchema] = []
    additional_info: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OrderForOrderingSchema(BaseModel):
    id: int
    route_id: int
    client_full_name: str
    address: str
    date: date_
    weight: Optional[int]
    city: CitySchema

    model_config = ConfigDict(from_attributes=True)


class RouteAssignmentSchema(BaseModel):
    route_id: int
    employee_id: int

    model_config = ConfigDict(from_attributes=True)


class RouteAssignmentUpsert(BaseModel):
    route_id: int
    employee_id: Optional[int] = None
    date: date_

    model_config = ConfigDict(from_attributes=False)


class ReorderPayload(BaseModel):
    old_order_id_list: List[int]
    new_order_id_list: List[int]
    change_route: bool
    old_route_id: Optional[int] = None
    new_route_id: Optional[int] = None
    moved_order_id: Optional[int] = None


class RouteAdditionalUpsert(BaseModel):
    route_id: int
    date: date_
    additional_info: str = ""

    model_config = ConfigDict(from_attributes=False)


class RouteAdditionalResponse(BaseModel):
    route_id: int
    date: date_
    additional_info: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
