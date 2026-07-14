from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app import models
from app.services.mpesa import MpesaService
from app.services.billing import BillingService

router = APIRouter(
    prefix="/mpesa",
    tags=["M-Pesa"]
)

limiter = Limiter(key_func=get_remote_address)


@router.post("/pay")
@limiter.limit("3/minute")
def initiate_payment(
    request: Request,
    package_id: int,
    phone_number: str,
    db: Session = Depends(get_db)
):
    phone_number = phone_number.strip()

    if phone_number.startswith("0"):
        phone_number = "254" + phone_number[1:]
    elif phone_number.startswith("+"):
        phone_number = phone_number[1:]

    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone == phone_number)
        .first()
    )

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

    mpesa = MpesaService()
    result = mpesa.stk_push(
        phone_number=phone_number,
        amount=int(package.price),
        account_reference=f"payment_{payment.id}",
        description="WiFi Payment"
    )

    payment.checkout_request_id = result.get("CheckoutRequestID")
    db.commit()

    return {
        "message": "STK Push sent, check your phone",
        "payment_id": payment.id,
        "checkout_request_id": result.get("CheckoutRequestID")
    }


@router.post("/callback")
async def mpesa_callback(request: dict, db: Session = Depends(get_db)):
    body = request["Body"]["stkCallback"]

    checkout_request_id = body["CheckoutRequestID"]
    result_code = body["ResultCode"]

    payment = (
        db.query(models.Payment)
        .filter(models.Payment.checkout_request_id == checkout_request_id)
        .first()
    )

    if not payment:
        return {"ResultCode": 0, "ResultDesc": "Payment not found, ignored"}

    if result_code == 0:
        items = body["CallbackMetadata"]["Item"]
        receipt = next((i["Value"] for i in items if i["Name"] == "MpesaReceiptNumber"), None)

        payment.mpesa_receipt = receipt
        payment.status = "success"
        db.commit()

        billing = BillingService(db)
        billing.activate_payment(payment.id)

    else:
        payment.status = "failed"
        db.commit()

    return {"ResultCode": 0, "ResultDesc": "Accepted"}

'''
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.services.mpesa import MpesaService
from app.services.billing import BillingService

router = APIRouter(
    prefix="/mpesa",
    tags=["M-Pesa"]
)

@router.post("/pay")
def initiate_payment(
    package_id: int,
    phone_number: str,
    db: Session = Depends(get_db)
):
    phone_number = phone_number.strip()

    if phone_number.startswith("0"):
        phone_number = "254" + phone_number[1:]
    elif phone_number.startswith("+"):
        phone_number = phone_number[1:]

    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone == phone_number)
        .first()
    )

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

    mpesa = MpesaService()
    result = mpesa.stk_push(
        phone_number=phone_number,
        amount=int(package.price),
        account_reference=f"payment_{payment.id}",
        description="WiFi Payment"
    )

    payment.checkout_request_id = result.get("CheckoutRequestID")
    db.commit()

    return {
        "message": "STK Push sent, check your phone",
        "payment_id": payment.id,
        "checkout_request_id": result.get("CheckoutRequestID")
    }

@router.post("/pay")
def initiate_payment(
    customer_id: int,
    package_id: int,
    phone_number: str,
    db: Session = Depends(get_db)
):
    package = db.query(models.Package).filter(models.Package.id == package_id).first()

    payment = models.Payment(
        customer_id=customer_id,
        package_id=package_id,
        amount=package.price,
        status="pending"
    )

    db.add(payment)
    db.commit()
    db.refresh(payment)

    mpesa = MpesaService()
    result = mpesa.stk_push(
        phone_number=phone_number,
        amount=int(package.price),
        account_reference=f"payment_{payment.id}",
        description="WiFi Payment"
    )

    payment.checkout_request_id = result.get("CheckoutRequestID")
    db.commit()

    return {
        "message": "STK Push sent, check your phone",
        "payment_id": payment.id,
        "checkout_request_id": result.get("CheckoutRequestID")
    }


@router.post("/callback")
async def mpesa_callback(request: dict, db: Session = Depends(get_db)):
    body = request["Body"]["stkCallback"]

    checkout_request_id = body["CheckoutRequestID"]
    result_code = body["ResultCode"]

    payment = (
        db.query(models.Payment)
        .filter(models.Payment.checkout_request_id == checkout_request_id)
        .first()
    )

    if not payment:
        return {"ResultCode": 0, "ResultDesc": "Payment not found, ignored"}

    if result_code == 0:
        items = body["CallbackMetadata"]["Item"]
        receipt = next((i["Value"] for i in items if i["Name"] == "MpesaReceiptNumber"), None)

        payment.mpesa_receipt = receipt
        payment.status = "success"
        db.commit()

        billing = BillingService(db)
        billing.activate_payment(payment.id)

    else:
        payment.status = "failed"
        db.commit()

    return {"ResultCode": 0, "ResultDesc": "Accepted"}
'''