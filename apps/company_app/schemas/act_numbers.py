from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, computed_field
from datetime import date as date_

from models.enums.verification import VerificationLegalEntity


class ActNumberForm(BaseModel):
    act_number: Optional[int] = Field(None)
    client_full_name: Optional[str] = Field("", max_length=255)
    client_phone: Optional[str] = Field("", max_length=20)
    address: Optional[str] = Field("", max_length=255)
    verification_date: Optional[date_] = Field(None)
    city_id: Optional[int] = Field(None)
    legal_entity: Optional[VerificationLegalEntity] = Field(None)
    series_id: Optional[int] = Field(None)


class CityOrSeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str


class ActNumberOut(BaseModel):
    id: int
    act_number: int

    series: Optional[CityOrSeriesOut]
    city: Optional[CityOrSeriesOut]

    client_full_name: Optional[str]
    client_phone: Optional[str]
    address: Optional[str]

    legal_entity: Optional[VerificationLegalEntity] = None
    count: Optional[int] = None
    is_deleted: bool = False

    verification_date: Optional[date_] = None

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    @computed_field(return_type=str, alias="verification_date_strftime")
    def _verification_date_strftime(self) -> str:
        if self.verification_date:
            return self.verification_date.strftime("%d.%m.%Y")
        return ""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class ActNumbersPage(BaseModel):
    items: List[ActNumberOut]
    page: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)
