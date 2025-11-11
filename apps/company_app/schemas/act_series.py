from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ActSeriesForm(BaseModel):
    name: Optional[str] = Field("", max_length=60)


class ActSeriesOut(BaseModel):
    id: int
    name: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class ActSeriesPage(BaseModel):
    items: List[ActSeriesOut]
    page: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
