from typing import List
from pydantic import BaseModel, ConfigDict, Field


class CityForm(BaseModel):
    name: str = Field(..., max_length=255)


class CityOut(BaseModel):
    id: int
    name: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class CitiesPage(BaseModel):
    items: List[CityOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
