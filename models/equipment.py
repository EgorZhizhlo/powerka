import base64
from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, Integer, String, ForeignKey, LargeBinary, Boolean, Enum
)

from infrastructure.db.base import BaseModel

from models.enums import EquipmentType
from models.mixins import TimeMixin
from models.associations import equipments_verifiers


class EquipmentModel(BaseModel, TimeMixin):
    __tablename__ = 'equipments'

    image = Column(LargeBinary, nullable=True)
    image2 = Column(LargeBinary, nullable=True)
    document_pdf = Column(LargeBinary, nullable=True)

    name = Column(String(80), nullable=False)
    full_name = Column(String(150), nullable=False)
    factory_number = Column(String(30), nullable=False)
    inventory_number = Column(Integer, nullable=False)
    type = Column(
        Enum(EquipmentType, name='equipment_type_enum'),
        nullable=False
    )
    register_number = Column(String(100))
    list_number = Column(String(100))
    is_opt = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)

    measurement_range = Column(String(255))
    error_or_uncertainty = Column(String(255))
    software_identifier = Column(String(255))

    year_of_issue = Column(Integer)
    manufacturer_country = Column(String(120))
    manufacturer_name = Column(String(255))
    commissioning_year = Column(Integer)
    ownership_document = Column(String(255))
    storage_place = Column(String(255))

    company_id = Column(
        Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    activity_id = Column(
        Integer, ForeignKey("company_activities.id", ondelete='SET NULL'),
        nullable=True)
    si_type_id = Column(
        Integer, ForeignKey("company_si_types.id", ondelete='SET NULL'),
        nullable=True)

    # --- relationships ---
    activity = relationship(
        "CompanyActivityModel",
        back_populates="equipments",
        passive_deletes=True
    )
    si_type = relationship(
        "CompanySiTypeModel",
        back_populates="equipments",
        passive_deletes=True
    )
    verifiers = relationship(
        'VerifierModel',
        secondary=equipments_verifiers,
        back_populates='equipments'
    )
    verifier_history = relationship(
        "VerifierEquipmentHistoryModel",
        back_populates="equipment",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    equipment_info = relationship(
        'EquipmentInfoModel',
        back_populates='equipment',
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EquipmentInfoModel.id"
    )
    company = relationship(
        'CompanyModel',
        back_populates='equipments'
    )
    verifications = relationship(
        "VerificationEntryModel",
        secondary="verification_entries_equipments",
        back_populates="equipments",
        passive_deletes=True
    )

    def get_image(self):
        return (
            base64.b64encode(self.image).decode('utf-8')
            if self.image
            else None)

    def get_image2(self):
        return (
            base64.b64encode(self.image2).decode('utf-8')
            if self.image2
            else None)
