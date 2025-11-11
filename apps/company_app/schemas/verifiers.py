from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class VerifierForm(BaseModel):
    last_name: str = Field(...)
    name: str = Field(...)
    patronymic: str = Field(...)
    snils: str = Field(...)
    equipments: Optional[List[int]] = Field(default_factory=list)


class EquipmentOut(BaseModel):
    id: int
    name: str
    factory_number: str
    inventory_number: int
    model_config = ConfigDict(from_attributes=True)


class VerifierOut(BaseModel):
    id: int
    last_name: str
    name: str
    patronymic: str
    snils: str
    is_deleted: bool = False
    equipments: List[EquipmentOut]

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class VerifiersPage(BaseModel):
    items: List[VerifierOut]
    page: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
