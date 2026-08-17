import uuid
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.services.pesapal_service import PesapalService
from app.services.billing import BillingService
from app.config import MPESA_CALLBACK_URL  # we'll reuse your domain, different path

router = APIRouter(
    prefix="/pesapal",
    tags=["Pesapal (backup)"]
)

PESAPAL_CALLBACK_URL = "https://shadownet.fyi/pesapal/callback"


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

    pesapal = PesapalService()
    token = pesapal.authenticate()
    ipn_id = pesapal.register_ipn(token, PESAPAL_CALLBACK_URL)

    order = pesapal.submit_order(
        token=token,
        notification_id=ipn_id,
        order_id=str(uuid.uuid4()),
        amount=float(package.price),
        phone_number=phone_number,
        callback_url=PESAPAL_CALLBACK_URL
    )

    payment.checkout_request_id = order.get("order_tracking_id")
    db.commit()

    return {
        "message": "Redirect to complete payment",
        "payment_id": payment.id,
        "redirect_url": order.get("redirect_url")
    }


@router.get("/callback")
def pesapal_callback(OrderTrackingId: str, OrderMerchantReference: str, db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.checkout_request_id == OrderTrackingId).first()
    if not payment:
        return {"status": "ignored"}

    pesapal = PesapalService()
    token = pesapal.authenticate()
    status_result = pesapal.get_transaction_status(token, OrderTrackingId)

    if status_result.get("payment_status_description") == "Completed":
        payment.status = "success"
        db.commit()
        billing = BillingService(db)
        billing.activate_payment(payment.id)
    else:
        payment.status = "failed"
        db.commit()

    return {"status": "processed"}