from typing import List, Optional, Dict
from pydantic import (
    BaseModel, ConfigDict, Field,
    field_validator, model_validator
)
import json


class VerificationReportForm(BaseModel):
    name: str = Field(..., max_length=100)

    fields_order: List[str] = Field(default_factory=list)
    fields_state: Dict[str, bool] = Field(default_factory=dict)

    for_verifier: Optional[bool] = Field(False)
    for_auditor: Optional[bool] = Field(False)

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


class VerificationReportListItem(BaseModel):
    id: int
    name: str
    fields_order: Optional[str] = ""

    for_verifier: Optional[bool] = False
    for_auditor: Optional[bool] = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class VerificationReportDetail(BaseModel):
    id: int
    name: str
    fields_order: Optional[str] = ""

    employee_name: Optional[bool] = False
    verification_date: Optional[bool] = False
    city: Optional[bool] = False
    address: Optional[bool] = False
    client_name: Optional[bool] = False
    si_type: Optional[bool] = False
    registry_number: Optional[bool] = False
    factory_number: Optional[bool] = False
    location_name: Optional[bool] = False
    meter_info: Optional[bool] = False
    end_verification_date: Optional[bool] = False
    series_name: Optional[bool] = False
    act_number: Optional[bool] = False
    verification_result: Optional[bool] = False
    verification_number: Optional[bool] = False
    qh: Optional[bool] = False
    modification_name: Optional[bool] = False
    water_type: Optional[bool] = False
    method_name: Optional[bool] = False
    reference: Optional[bool] = False
    seal: Optional[bool] = False
    phone_number: Optional[bool] = False
    verifier_name: Optional[bool] = False
    manufacture_year: Optional[bool] = False
    reason_name: Optional[bool] = False
    interval: Optional[bool] = False

    additional_checkbox_1: Optional[bool] = False
    additional_checkbox_2: Optional[bool] = False
    additional_checkbox_3: Optional[bool] = False
    additional_checkbox_4: Optional[bool] = False
    additional_checkbox_5: Optional[bool] = False

    additional_input_1: Optional[bool] = False
    additional_input_2: Optional[bool] = False
    additional_input_3: Optional[bool] = False
    additional_input_4: Optional[bool] = False
    additional_input_5: Optional[bool] = False

    for_verifier: Optional[bool] = False
    for_auditor: Optional[bool] = False

    created_at_strftime_full: str = ""
    updated_at_strftime_full: str = ""

    model_config = ConfigDict(from_attributes=True)


class VerificationReportsPage(BaseModel):
    items: List[VerificationReportListItem]
    page: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
