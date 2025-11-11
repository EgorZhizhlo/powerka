from typing import Optional
from pydantic import BaseModel, Field

from datetime import date as date_


class EquipmentInfoCreate(BaseModel):
    verif_date: Optional[date_]
    verif_limit_date: Optional[date_]
    info: Optional[str] = Field("", max_length=200)
