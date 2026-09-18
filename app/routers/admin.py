from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import get_db
from app import models
from app.auth import verify_admin_key
from app.services.billing import BillingService

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)]
)


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/customers")
def list_customers(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()
    result = []

    for c in customers:
        latest_payment = (
            db.query(models.Payment)
            .filter(models.Payment.customer_id == c.id)
            .order_by(models.Payment.paid_at.desc())
            .first()
        )

        if c.suspended:
            status = "Suspended"
        elif latest_payment and latest_payment.activated and latest_payment.expires_at and latest_payment.expires_at > utc_now():
            status = "Active"
        elif latest_payment and latest_payment.activated:
            status = "Expired"
        else:
            status = "No active plan"

        result.append({
            "id": c.id,
            "phone": c.phone,
            "name": c.name,
            "status": status,
            "expires_at": latest_payment.expires_at if latest_payment else None,
            "latest_payment_id": latest_payment.id if latest_payment else None
        })

    return result


@router.get("/payments/today")
def payments_today(db: Session = Depends(get_db)):
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

    payments = (
        db.query(models.Payment)
        .filter(models.Payment.paid_at >= today_start)
        .order_by(models.Payment.paid_at.desc())
        .all()
    )

    total = sum(p.amount for p in payments if p.status == "success")

    return {
        "total_revenue": total,
        "count": len(payments),
        "payments": [
            {
                "id": p.id,
                "customer_phone": p.customer.phone if p.customer else None,
                "amount": p.amount,
                "status": p.status,
                "paid_at": p.paid_at
            }
            for p in payments
        ]
    }


@router.get("/packages")
def list_packages(db: Session = Depends(get_db)):
    return db.query(models.Package).all()


@router.get("/packages/{package_id}")
def get_package(package_id: int, db: Session = Depends(get_db)):
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        return {"error": "Package not found"}
    return package


@router.put("/packages/{package_id}/price")
def update_package_price(package_id: int, price: int, db: Session = Depends(get_db)):
    package = db.query(models.Package).filter(models.Package.id == package_id).first()

    if not package:
        return {"error": "Package not found"}

    package.price = price
    db.commit()

    return {"message": "Price updated", "package_id": package.id, "new_price": package.price}


UNIT_TO_SECONDS = {
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
    "month": 2592000, "months": 2592000,
}


@router.post("/packages")
def create_package(
    name: str,
    duration_value: int,
    duration_unit: str,
    price: int,
    download_speed: str,
    upload_speed: str,
    shared_users: int = 1,
    daily_quota_mb: Optional[int] = None,
    throttle_upload: Optional[str] = None,
    throttle_download: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Create a new package/bundle.

    Speed fields (download_speed, upload_speed) must include the unit
    MikroTik expects, e.g. "3M", not "3" — a bare number is interpreted
    as bits/sec, not megabits, and effectively breaks the package.

    daily_quota_mb, throttle_upload and throttle_download are optional
    and only needed for fair-use bundles: once a customer on this
    package uses daily_quota_mb worth of data in a calendar day, they
    are automatically switched to throttle_upload/throttle_download
    speed until the next day. Leave all three unset for packages that
    don't need a fair-use cap (e.g. short/hourly packages).
    """
    unit = duration_unit.lower()
    if unit not in UNIT_TO_SECONDS:
        return {"error": f"Invalid duration_unit '{duration_unit}'"}

    if (daily_quota_mb or throttle_upload or throttle_download) and not (
        daily_quota_mb and throttle_upload and throttle_download
    ):
        return {
            "error": "daily_quota_mb, throttle_upload and throttle_download must "
                     "all be provided together, or all left unset"
        }

    package = models.Package(
        name=name,
        duration_seconds=duration_value * UNIT_TO_SECONDS[unit],
        price=price,
        download_speed=download_speed,
        upload_speed=upload_speed,
        shared_users=shared_users,
        daily_quota_mb=daily_quota_mb,
        throttle_upload=throttle_upload,
        throttle_download=throttle_download,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


@router.put("/packages/{package_id}")
def update_package(
    package_id: int,
    name: Optional[str] = None,
    duration_value: Optional[int] = None,
    duration_unit: Optional[str] = None,
    price: Optional[int] = None,
    download_speed: Optional[str] = None,
    upload_speed: Optional[str] = None,
    shared_users: Optional[int] = None,
    daily_quota_mb: Optional[int] = None,
    throttle_upload: Optional[str] = None,
    throttle_download: Optional[str] = None,
    clear_fair_use: bool = False,
    active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Edit any field(s) of an existing package/bundle. Only fields you
    pass are changed — everything else stays as-is.

    To remove fair-use throttling from a package entirely, pass
    clear_fair_use=true (this takes priority over any daily_quota_mb /
    throttle_upload / throttle_download values sent in the same call).

    Note: editing an existing package's speed or fair-use fields does
    not retroactively change the MikroTik profile for customers already
    activated on it — new values apply the next time a payment for this
    package is activated. Existing sessions are unaffected until then.
    """
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        return {"error": "Package not found"}

    if name is not None:
        package.name = name

    if duration_value is not None or duration_unit is not None:
        if duration_value is None or duration_unit is None:
            return {"error": "duration_value and duration_unit must be provided together"}
        unit = duration_unit.lower()
        if unit not in UNIT_TO_SECONDS:
            return {"error": f"Invalid duration_unit '{duration_unit}'"}
        package.duration_seconds = duration_value * UNIT_TO_SECONDS[unit]

    if price is not None:
        package.price = price
    if download_speed is not None:
        package.download_speed = download_speed
    if upload_speed is not None:
        package.upload_speed = upload_speed
    if shared_users is not None:
        package.shared_users = shared_users
    if active is not None:
        package.active = active

    if clear_fair_use:
        package.daily_quota_mb = None
        package.throttle_upload = None
        package.throttle_download = None
    else:
        if daily_quota_mb is not None:
            package.daily_quota_mb = daily_quota_mb
        if throttle_upload is not None:
            package.throttle_upload = throttle_upload
        if throttle_download is not None:
            package.throttle_download = throttle_download

    db.commit()
    db.refresh(package)
    return package


@router.delete("/packages/{package_id}")
def delete_package(package_id: int, db: Session = Depends(get_db)):
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        return {"error": "Package not found"}

    has_payments = db.query(models.Payment).filter(models.Payment.package_id == package_id).first()
    if has_payments:
        package.active = False
        db.commit()
        return {"message": "Package has payment history — marked inactive instead of deleted", "package_id": package_id}

    db.delete(package)
    db.commit()
    return {"message": "Package deleted", "package_id": package_id}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    billing = BillingService(db)
    result = billing.delete_customer(customer_id)

    if not result:
        return {"error": "Customer not found"}

    return {"message": "Customer deleted"}
