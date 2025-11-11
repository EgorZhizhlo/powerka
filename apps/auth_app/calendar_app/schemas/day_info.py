from pydantic import BaseModel


class DayInfoSchema(BaseModel):
    day_info: str
