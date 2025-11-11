from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class RegistryNumberCreate(BaseModel):
    registry_number: Optional[str]
    si_type: Optional[str]
    mpi_hot: Optional[int] = None
    mpi_cold: Optional[int] = None
    method_id: Optional[int]
    modifications: Optional[List[int]] = []


class MethodOut(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class ModificationOut(BaseModel):
    id: int
    modification_name: str
    model_config = ConfigDict(from_attributes=True)


class RegistryNumberOut(BaseModel):
    id: int
    registry_number: str
    si_type: str
    mpi_hot: Optional[int]
    mpi_cold: Optional[int]
    method: MethodOut
    modifications: List[ModificationOut]
    is_deleted: bool = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class RegistryNumberPage(BaseModel):
    items: List[RegistryNumberOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
