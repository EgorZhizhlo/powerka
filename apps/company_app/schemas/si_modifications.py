from typing import List
from pydantic import BaseModel, ConfigDict


class SiModificationCreate(BaseModel):
    modification_name: str


class SiModificationOut(BaseModel):
    id: int
    modification_name: str
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class ModificationsPage(BaseModel):
    items: List[SiModificationOut]
    page: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
