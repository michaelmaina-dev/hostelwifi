# app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.services.billing import BillingService
from app.models import Customer
from datetime import datetime, timezone


def check_expired_payments():
    db = SessionLocal()
    try:
        billing = BillingService(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check per-customer, not per-payment-row: a customer with several
        # payments (repeat purchases) can have old, individually-expired
        # rows sitting alongside a currently-valid one (duration stacking
        # keeps only the latest row's expires_at meaningful). Suspending on
        # any single expired row — even an old, superseded one — wrongly
        # cuts off customers who are still validly paid up.
        customers = db.query(Customer).filter(Customer.suspended == False).all()

        for customer in customers:
            has_activated_payment = any(p.activated for p in customer.payments)
            still_valid = any(
                p.activated and p.expires_at and p.expires_at > now
                for p in customer.payments
            )

            if has_activated_payment and not still_valid:
                try:
                    billing.suspend_customer(customer.id)
                except Exception as e:
                    print(f"[scheduler] Failed to suspend customer {customer.id}: {e}")

    finally:
        db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(check_expired_payments, "interval", seconds=10)