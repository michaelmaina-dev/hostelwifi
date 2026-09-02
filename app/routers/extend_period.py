from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.billing import BillingService
from app.auth import verify_admin_key

router = APIRouter(
    prefix="/extend_period",
    tags=["extend_period"]
)


@router.post("/extend/{payment_id}")
def extend_customer(
    payment_id: int,
    extra_seconds: int = None,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_key)
):
    billing = BillingService(db)
    result = billing.extend_customer(payment_id, extra_seconds=extra_seconds)

    if not result:
        raise HTTPException(status_code=404, detail="Payment not found or not yet activated")

    return {
        "message": "Payment extended",
        "payment_id": result.id,
        "new_expiry": result.expires_at
    }
