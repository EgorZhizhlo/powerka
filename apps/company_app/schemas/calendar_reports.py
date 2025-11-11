from typing import List, Optional, Dict
from pydantic import (
    BaseModel, ConfigDict, Field,
    field_validator, model_validator
)
import json


class CalendarReportForm(BaseModel):
    name: str = Field(..., max_length=100)

    # Порядок полей и их состояние
    fields_order: List[str] = Field(default_factory=list)
    fields_state: Dict[str, bool] = Field(default_factory=dict)

    # Дополнительные параметры
    for_auditor: Optional[bool] = Field(False)
    for_dispatcher1: Optional[bool] = Field(False)
    for_dispatcher2: Optional[bool] = Field(False)
    no_date: Optional[bool] = Field(False)

    @field_validator('fields_order', mode='before')
    @classmethod
    def parse_fields_order(cls, v):
        if isinstance(v, str):
            if not v or v.strip() == '':
                return []
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    @field_validator('fields_state', mode='before')
    @classmethod
    def parse_fields_state(cls, v):
        if isinstance(v, str):
            if not v or v.strip() == '':
                return {}
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v

    @model_validator(mode='after')
    def sync_fields_order_with_state(self):
        if self.fields_state:
            self.fields_order = [
                field for field in self.fields_order
                if self.fields_state.get(field, False) is True
            ]
        return self


class CalendarReportListItem(BaseModel):
    id: int
    name: str
    fields_order: Optional[str] = ""

    for_auditor: Optional[bool] = False
    for_dispatcher1: Optional[bool] = False
    for_dispatcher2: Optional[bool] = False
    no_date: Optional[bool] = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class CalendarReportDetail(BaseModel):
    id: int
    name: str
    fields_order: Optional[str] = ""

    dispatcher: Optional[bool] = False
    route: Optional[bool] = False
    date: Optional[bool] = False
    address: Optional[bool] = False
    phone_number: Optional[bool] = False
    sec_phone_number: Optional[bool] = False
    client_full_name: Optional[bool] = False
    legal_entity: Optional[bool] = False
    counter_number: Optional[bool] = False
    water_type: Optional[bool] = False
    price: Optional[bool] = False
    status: Optional[bool] = False
    additional_info: Optional[bool] = False
    deleted_at: Optional[bool] = False

    for_auditor: Optional[bool] = False
    for_dispatcher1: Optional[bool] = False
    for_dispatcher2: Optional[bool] = False
    no_date: Optional[bool] = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class CalendarReportOut(BaseModel):
    id: int
    name: str
    fields_order: Optional[str] = ""

    for_auditor: Optional[bool] = False
    for_dispatcher1: Optional[bool] = False
    for_dispatcher2: Optional[bool] = False
    no_date: Optional[bool] = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class CalendarReportsPage(BaseModel):
    items: List[CalendarReportListItem]
    page: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
