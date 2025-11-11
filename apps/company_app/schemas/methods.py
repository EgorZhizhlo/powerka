from typing import List
from pydantic import BaseModel, ConfigDict


class MethodForm(BaseModel):
    name: str


class MethodOut(BaseModel):
    id: int
    name: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class MethodsPage(BaseModel):
    items: List[MethodOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
