from pydantic import BaseModel, Field
from typing import Optional
from datetime import date as date_

from core.config import settings


class DynamicReportFilters(BaseModel):
    start_date: Optional[date_] = None
    end_date: Optional[date_] = None
    employee_id: Optional[int] = Field(
        None,
        ge=1,
        le=settings.max_int
    )
