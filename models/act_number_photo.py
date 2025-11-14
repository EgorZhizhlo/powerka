from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, ForeignKey

from infrastructure.db.base import BaseModel
from models.mixins import TimeMixin


class ActNumberPhotoModel(BaseModel, TimeMixin):
    __tablename__ = 'act_number_photos'

    act_number_id = Column(
        Integer,
        ForeignKey("act_numbers.id", ondelete="CASCADE"),
        nullable=False
    )

    file_name = Column(String, nullable=False)
    url = Column(String, nullable=True)

    act_number = relationship("ActNumberModel", back_populates="photos")
