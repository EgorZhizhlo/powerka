from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean,
    Date, Float, CheckConstraint, Enum
)
from infrastructure.db.base import BaseModel
from core.utils.time_utils import datetime_utc_now
from models.enums import (
    OrderWaterType,
    OrderStatus,
    VerificationLegalEntity
)


class OrderModel(BaseModel):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "counter_number >= 0", name="ck_counter_number_non_negative"
        ),
        CheckConstraint(
            "weight >= 0", name="ck_weight_non_negative"
        ),
        CheckConstraint(
            "counter_number <= 10", name="ck_counter_number_max_10"
        ),
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=datetime_utc_now,
        onupdate=datetime_utc_now,
        nullable=False
    )
    deleted_at = Column(DateTime(timezone=True))

    date = Column(Date)
    date_of_get = Column(
        DateTime(timezone=True),
        default=datetime_utc_now,
        nullable=False
    )

    client_full_name = Column(String(255))
    address = Column(String(255), nullable=False)
    phone_number = Column(String(18), nullable=False)
    sec_phone_number = Column(String(18))

    legal_entity = Column(
        Enum(VerificationLegalEntity, name="verification_legal_entity_enum"),
        nullable=True
    )

    counter_number = Column(Integer, default=0, nullable=False)

    water_type = Column(
        Enum(OrderWaterType, name="order_water_type_enum"),
        nullable=False
    )

    price = Column(Float, nullable=True)
    additional_info = Column(String(255))

    weight = Column(Integer)

    status = Column(
        Enum(OrderStatus, name="order_status_enum"),
        nullable=False,
        default=OrderStatus.pending
    )

    no_date = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    route_id = Column(
        Integer,
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True
    )
    city_id = Column(
        Integer,
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True
    )
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    dispatcher_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )

    # --- relationships ---
    dispatcher = relationship("EmployeeModel", back_populates="order")
    company = relationship("CompanyModel", back_populates="orders")
    route = relationship("RouteModel", back_populates="orders")
    city = relationship("CityModel", back_populates="order")
