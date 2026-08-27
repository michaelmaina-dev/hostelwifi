from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

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
    db: Session = Depends(get_db)
):
    unit = duration_unit.lower()
    if unit not in UNIT_TO_SECONDS:
        return {"error": f"Invalid duration_unit '{duration_unit}'"}

    package = models.Package(
        name=name,
        duration_seconds=duration_value * UNIT_TO_SECONDS[unit],
        price=price,
        download_speed=download_speed,
        upload_speed=upload_speed,
        shared_users=shared_users
    )
    db.add(package)
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