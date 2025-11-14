from pydantic import BaseModel, field_validator
from datetime import date


class VriRequestSchema(BaseModel):
    date_from: date
    date_to: date

    @field_validator("date_to")
    def validate_date_range(cls, v, values):
        date_from = values.get("date_from")
        if date_from and v < date_from:
            raise ValueError('"date_to" должно быть больше или равно "date_from"')
        return v
