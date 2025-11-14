from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, ForeignKey,
    Enum, UniqueConstraint, CheckConstraint
)

from infrastructure.db.base import BaseModel

from models.enums import VerificationLegalEntity
from models.mixins import TimeMixin


class ActNumberModel(BaseModel, TimeMixin):
    __tablename__ = 'act_numbers'
    __table_args__ = (
        UniqueConstraint(
            "act_number", "company_id", "series_id",
            name="uq_act_number_company_series"
        ),
        CheckConstraint(
            "count >= 0 AND count <= 4",
            name="ck_act_number_count_range"
        ),
    )

    act_number = Column(Integer, nullable=False)
    client_full_name = Column(String(255), nullable=True)
    client_phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=False)
    verification_date = Column(Date, nullable=False)
    legal_entity = Column(
        Enum(VerificationLegalEntity, name='verification_legal_entity_enum'),
        nullable=False
    )
    count = Column(Integer, default=4, nullable=False)

    is_deleted = Column(Boolean, default=False)

    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    city_id = Column(
        Integer,
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True
    )
    series_id = Column(
        Integer,
        ForeignKey("series.id", ondelete="SET NULL"),
        nullable=True
    )

    photos = relationship(
        "ActNumberPhotoModel",
        back_populates="act_number",
        cascade="all, delete-orphan"
    )

    series = relationship(
        "ActSeriesModel",
        back_populates="act_number",
        passive_deletes=True
    )
    city = relationship(
        "CityModel",
        back_populates="act_numbers",
        passive_deletes=True
    )
    verification = relationship(
        "VerificationEntryModel",
        back_populates="act_number",
        passive_deletes=True
    )
    company = relationship(
        "CompanyModel",
        back_populates="act_number",
        passive_deletes=True
    )
