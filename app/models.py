from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    BigInteger,
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

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    suspended = Column(Boolean, default=False)

    
    '''current_package_id = Column(
        Integer,
        ForeignKey("packages.id"),
        nullable=True
    )'''

    payments = relationship("Payment", back_populates="customer")

    daily_usage = relationship("DailyUsage", back_populates="customer")


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

    shared_users = Column(Integer, default=1)

    # --- Fair-use / bundle fields ---
    # daily_quota_mb: total MB a customer on this package can use per
    # calendar day before being throttled. None = no daily cap (typical
    # for short/hourly packages that don't need one).
    daily_quota_mb = Column(Integer, nullable=True)

    # throttle_upload / throttle_download: rate applied once a customer
    # crosses daily_quota_mb for the day (e.g. "1.5M" / "4M"). Both must
    # be set alongside daily_quota_mb for throttling to actually engage —
    # see BillingService.check_daily_quotas.
    throttle_upload = Column(String, nullable=True)
    throttle_download = Column(String, nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"))

    package_id = Column(Integer, ForeignKey("packages.id"))

    amount = Column(Float)

    mpesa_receipt = Column(String)

    status = Column(String)

    paid_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    customer = relationship("Customer", back_populates="payments")

    package = relationship("Package", back_populates="payments")

    activated = Column(Boolean, default=False)
    

    expires_at = Column(DateTime, nullable=True)

    checkout_request_id = Column(String, nullable=True)

    hotspot_password = Column(String, nullable=True)


class DailyUsage(Base):
    """Tracks a customer's accumulated data usage for a single calendar
    day, so fair-use throttling (see BillingService.check_daily_quotas)
    survives router polling gaps and mid-day reconnects."""

    __tablename__ = "daily_usage"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"))

    date = Column(Date, nullable=False)

    # Running total for the day, accumulated as deltas between polls.
    bytes_used = Column(BigInteger, default=0)

    # Last raw cumulative counter seen from the router for the customer's
    # current session. A drop in this value on the next poll means the
    # session restarted (disconnect/reconnect), not that usage went down.
    last_session_bytes = Column(BigInteger, default=0)

    throttled = Column(Boolean, default=False)

    customer = relationship("Customer", back_populates="daily_usage")
