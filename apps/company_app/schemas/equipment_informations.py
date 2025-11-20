from typing import Optional
from pydantic import BaseModel, Field

from datetime import date as date_


class EquipmentInfoCreate(BaseModel):
    date_from: Optional[date_]
    date_to: Optional[date_]
    info: Optional[str] = Field("", max_length=200)
