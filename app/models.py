from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime
)

from sqlalchemy.orm import relationship

from datetime import datetime, timezone

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    phone = Column(String, unique=True, nullable=False)

    name = Column(String)

    mac_address = Column(String, unique=True, nullable=True)

    room = Column(String)

    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    
    '''current_package_id = Column(
        Integer,
        ForeignKey("packages.id"),
        nullable=True
    )'''

    payments = relationship("Payment", back_populates="customer")


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True)

    duration_seconds = Column(Integer)

    price = Column(Integer)

    download_speed = Column(String)

    upload_speed = Column(String)

    active = Column(Boolean, default=True)

    payments = relationship("Payment", back_populates="package")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"))

    package_id = Column(Integer, ForeignKey("packages.id"))

    amount = Column(Float)

    mpesa_receipt = Column(String)

    status = Column(String)

    paid_at = Column(DateTime, default=datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="payments")

    package = relationship("Package", back_populates="payments")

    activated = Column(Boolean, default=False)

    expires_at = Column(DateTime, nullable=True)

    checkout_request_id = Column(String, nullable=True)

    hotspot_password = Column(String, nullable=True)