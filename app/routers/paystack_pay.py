import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.services.paystack_service import PaystackService
from app.services.billing import BillingService

router = APIRouter(
    prefix="/paystack",
    tags=["Paystack (backup)"]
)


@router.post("/pay")
def initiate_payment(package_id: int, phone_number: str, db: Session = Depends(get_db)):
    phone_number = phone_number.strip()
    if phone_number.startswith("0"):
        phone_number = "254" + phone_number[1:]
    elif phone_number.startswith("+"):
        phone_number = phone_number[1:]

    customer = db.query(models.Customer).filter(models.Customer.phone == phone_number).first()
    if not customer:
        customer = models.Customer(phone=phone_number)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    package = db.query(models.Package).filter(models.Package.id == package_id).first()

    payment = models.Payment(
        customer_id=customer.id,
        package_id=package_id,
        amount=package.price,
        status="pending"
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    reference = f"payment_{payment.id}_{uuid.uuid4().hex[:8]}"

    paystack = PaystackService()
    result = paystack.charge_mpesa(
        amount=package.price,
        phone_number=phone_number,
        reference=reference
    )
    payment.checkout_request_id = reference
    db.commit()

    return {
        "message": "Check your phone to complete payment",
        "payment_id": payment.id,
        "status": result.get("data", {}).get("status")
    }


@router.post("/webhook")
async def paystack_webhook(request: dict, db: Session = Depends(get_db)):
    event = request.get("event")
    data = request.get("data", {})
    reference = data.get("reference")

    payment = db.query(models.Payment).filter(models.Payment.checkout_request_id == reference).first()
    if not payment:
        return {"status": "ignored"}

    if payment.activated:
        return {"status": "already_processed"}

    if event == "charge.success":
        payment.status = "success"
        db.commit()
        billing = BillingService(db)
        billing.activate_payment(payment.id)
    elif event in ("charge.failed",):
        payment.status = "failed"
        db.commit()

    return {"status": "received"}

@router.get("/status/{payment_id}")
def check_status(payment_id: int, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        return {"activated": False}

    return {
        "activated": payment.activated,
        "username": payment.customer.phone if payment.activated else None,
        "password": payment.hotspot_password if payment.activated else None
    }