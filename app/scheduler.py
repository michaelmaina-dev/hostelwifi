# app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.services.billing import BillingService
from app.models import Payment, Customer
from datetime import datetime


from datetime import datetime, timezone

def check_expired_payments():
    db = SessionLocal()
    try:
        billing = BillingService(db)

        expired = (
            db.query(Payment)
            .join(Customer)
            .filter(Payment.activated == True)
            .filter(Payment.expires_at < datetime.now(timezone.utc))
            .filter(Customer.suspended == False)
            .all()
        )

        print(f"[scheduler] Checked at {datetime.now(timezone.utc)} — found {len(expired)} expired payment(s)")

        for payment in expired:
            billing.suspend_customer(payment.customer_id)

    finally:
        db.close()

       
scheduler = BackgroundScheduler()
scheduler.add_job(check_expired_payments, "interval", seconds=10)