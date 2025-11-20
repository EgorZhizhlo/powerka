from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, Boolean, Enum
)

from infrastructure.db.base import BaseModel

from models.enums import EquipmentInfoType
from models.mixins import TimeMixin


class EquipmentInfoModel(BaseModel, TimeMixin):
    __tablename__ = 'equipment_info'

    type = Column(
        Enum(EquipmentInfoType, name='equipment_info_type_enum'),
        nullable=False
    )
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    info = Column(String(200))
    is_deleted = Column(Boolean, default=False)

    equipment_id = Column(
        Integer, ForeignKey('equipments.id', ondelete="CASCADE"),
        index=True, nullable=False)

    # --- relationships ---
    equipment = relationship(
        'EquipmentModel', back_populates='equipment_info')
