from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.billing import BillingService
from app.auth import verify_admin_key

router = APIRouter(
    prefix="/activate_pay",
    tags=["activate_pay"]
)


@router.post("/activate/{payment_id}")
def activate_payment(payment_id: int, db: Session = Depends(get_db), _: None = Depends(verify_admin_key)):
    billing = BillingService(db)
    result = billing.activate_payment(payment_id)

    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {"message": "Customer activated", "payment_id": result.id}