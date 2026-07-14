from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.billing import BillingService


router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


@router.post("", response_model=schemas.PaymentResponse)
def create_payment(
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db)
):

    customer = db.query(models.Customer).filter(
        models.Customer.id == payment.customer_id
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    package = db.query(models.Package).filter(
        models.Package.id == payment.package_id
    ).first()

    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    db_payment = models.Payment(
        customer_id=payment.customer_id,
        package_id=payment.package_id,
        amount=package.price,
        mpesa_receipt=payment.mpesa_receipt,
        status=payment.status
    )

    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)

    return db_payment


@router.get("")
def get_payments(db: Session = Depends(get_db)):
    return db.query(models.Payment).all()








