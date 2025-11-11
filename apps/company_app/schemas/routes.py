from typing import List
from pydantic import BaseModel, ConfigDict, Field


class RouteForm(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    day_limit: int = Field(..., ge=1, le=1000)
    color: str = Field(..., pattern=r'^[0-9A-Fa-f]{6}$', max_length=6)


class RouteOut(BaseModel):
    id: int
    name: str
    day_limit: int
    color: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class RoutesPage(BaseModel):
    items: List[RouteOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
