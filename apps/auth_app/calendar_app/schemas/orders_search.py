from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date as Date


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
    date: Optional[Date]

    model_config = ConfigDict(from_attributes=True)


class OrdersPaginated(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[OrderSchema]
