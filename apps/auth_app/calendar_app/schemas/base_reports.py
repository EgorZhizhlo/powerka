from typing import Optional
from pydantic import BaseModel


class EmployeeSchema(BaseModel):
    id: int
    last_name: Optional[str]
    name: Optional[str]
    patronymic: Optional[str]
    username: str


class RouteSchema(BaseModel):
    id: int
    name: str
