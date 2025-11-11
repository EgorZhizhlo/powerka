from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class MethodResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class SiModificationResponse(BaseModel):
    id: int
    modification_name: str

    model_config = ConfigDict(from_attributes=True)


class RegistryNumberResponse(BaseModel):
    id: int
    registry_number: str
    si_type: Optional[str] = None
    mpi_cold: Optional[int] = None
    mpi_hot: Optional[int] = None
    method: Optional[MethodResponse] = None
    modifications: List[SiModificationResponse] = []

    model_config = ConfigDict(from_attributes=True)
