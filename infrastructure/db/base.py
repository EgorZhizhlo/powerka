from sqlalchemy import Integer, Column
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs


class BaseModel(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей"""
    __abstract__ = True

    id = Column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
