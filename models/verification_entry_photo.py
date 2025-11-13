from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, ForeignKey

from infrastructure.db.base import BaseModel

from models.mixins import TimeMixin


class VerificationEntryPhotoModel(BaseModel, TimeMixin):
    __tablename__ = 'verification_entry_photos'

    verification_entry_id = Column(
        Integer,
        ForeignKey("verification_entries.id", ondelete="CASCADE"),
        nullable=False
    )

    file_name = Column(String, nullable=True)
    url = Column(String, nullable=True)

    verification_entry = relationship(
        "VerificationEntryModel",
        back_populates="verification_entry_photo"
    )
