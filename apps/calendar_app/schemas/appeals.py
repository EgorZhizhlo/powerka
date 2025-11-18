from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime as datetime_

from models.enums import AppealStatus


class DispatcherSchema(BaseModel):
    id: Optional[int]
    name: Optional[str]
    last_name: Optional[str]
    patronymic: Optional[str]
    username: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class AppealSchema(BaseModel):
    id: Optional[int]
    dispatcher: Optional[DispatcherSchema]
    date_of_get: Optional[datetime_]
    client_full_name: Optional[str]
    address: Optional[str]
    phone_number: Optional[str]
    additional_info: Optional[str]
    status: AppealStatus

    model_config = ConfigDict(from_attributes=True)


class AppealFormSchema(BaseModel):
    client_full_name: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    additional_info: Optional[str] = None
    status: AppealStatus = AppealStatus.accepted

    model_config = ConfigDict(from_attributes=True)


class AppealsPaginated(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[AppealSchema]
