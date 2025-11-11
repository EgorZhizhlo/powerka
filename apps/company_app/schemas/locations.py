from typing import List
from pydantic import BaseModel, ConfigDict, Field


class LocationForm(BaseModel):
    name: str = Field(..., max_length=60)


class LocationOut(BaseModel):
    id: int
    name: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class LocationsPage(BaseModel):
    items: List[LocationOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
