from typing import List
from pydantic import BaseModel, ConfigDict, Field


class ReasonForm(BaseModel):
    type: str = Field(...)
    name: str = Field(..., max_length=120)
    full_name: str = Field(..., max_length=255)


class ReasonOut(BaseModel):
    id: int
    type: str | None
    name: str
    full_name: str | None
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class ReasonsPage(BaseModel):
    items: List[ReasonOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
