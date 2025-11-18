from pydantic import BaseModel, field_validator
import re


class AppealWebHookForm(BaseModel):
    address: str
    phone_number: str
    client_full_name: str
    additional_info: str = ""

    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v):
        if v is not None:
            v = re.sub(r'[^\+\d]', '', v)
            if not v:
                raise ValueError('Неверный формат номера телефона')
        return v

    @field_validator('address')
    @classmethod
    def validate_address(cls, v):
        if v is not None:
            v = v.strip()
        return v

    @field_validator('client_full_name')
    @classmethod
    def validate_client_full_name(cls, v):
        if v is not None:
            v = v.strip()
        return v
