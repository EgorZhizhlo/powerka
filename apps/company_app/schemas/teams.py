from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class VerifierShort(BaseModel):
    id: int
    last_name: str
    name: str
    patronymic: str
    snils: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TeamOut(BaseModel):
    id: int
    name: str
    is_deleted: bool = False
    verifiers: List[VerifierShort] = []

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class TeamsPage(BaseModel):
    items: List[TeamOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)


class TeamCreate(BaseModel):
    name: str
    verifiers: Optional[List[int]] = []
