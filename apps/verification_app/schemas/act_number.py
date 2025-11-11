from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict
from models.enums import VerificationLegalEntity


class ActNumberResponse(BaseModel):
    act_number: int
    client_full_name: Optional[str] = None
    client_phone: Optional[str] = None
    address: Optional[str] = None
    verification_date: Optional[date] = None
    legal_entity: VerificationLegalEntity
    city_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
