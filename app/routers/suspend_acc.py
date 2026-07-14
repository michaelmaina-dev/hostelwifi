from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.billing import BillingService
from app.auth import verify_admin_key

router = APIRouter(
    prefix="/suspend_acc",
    tags=["suspend_acc"]
)

@router.post("/suspend/{customer_id}")
def suspend_customer(customer_id: int, db: Session = Depends(get_db), _: None = Depends(verify_admin_key)):
    ...
    billing = BillingService(db)
    result = billing.suspend_customer(customer_id)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return {"message": "Customer suspended", "customer_id": result.id}