from sqlalchemy.orm import Session

from app.models import Customer, Package, Payment
from app.services.mikrotik import MikroTikService
from datetime import datetime, timedelta, timezone
import secrets
import string


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_password(length=8):
    characters = string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


class BillingService:

    def __init__(self, db: Session):
        self.db = db
        self.router = MikroTikService()

    def activate_payment(self, payment_id: int):
        payment = (
            self.db.query(Payment)
            .filter(Payment.id == payment_id)
            .first()
        )

        if not payment:
            return None

        customer = payment.customer
        if not customer:
            return None

        package = payment.package
        if not package:
            return None

        username = customer.phone
        password = payment.mpesa_receipt if payment.mpesa_receipt else generate_password()

        profile_name = f"pkg_{package.id}"
        rate_limit = f"{package.upload_speed}/{package.download_speed}"

        self.router.ensure_profile(profile_name, rate_limit, shared_users=package.shared_users)

        self.router.create_hotspot_user(
            username=username,
            password=password,
            profile=profile_name
        )

        payment.hotspot_password = password       # 👈 fix: actually save it
        payment.activated = True
        payment.status = "success"                 # 👈 fix: keep status consistent
        payment.expires_at = utc_now() + timedelta(seconds=package.duration_seconds)

        customer.suspended = False                  # 👈 fix: clear suspension on (re)activation
        self.db.commit()

        return payment

    def suspend_customer(self, customer_id: int):
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            return None

        self.router.disable_hotspot_user(username=customer.phone)

        customer.suspended = True                   # 👈 fix: actually record it
        self.db.commit()

        return customer

    def extend_customer(self, payment_id: int):
        payment = (
            self.db.query(Payment)
            .filter(Payment.id == payment_id)
            .first()
        )

        if not payment:
            return None

        package = payment.package
        if not package:
            return None

        if not payment.expires_at:
            return None

        payment.expires_at = payment.expires_at + timedelta(seconds=package.duration_seconds)  # 👈 fix: add to existing, don't reset
        self.db.commit()

        return payment
    def delete_customer(self, customer_id: int):
            customer = (
                self.db.query(Customer)
                .filter(Customer.id == customer_id)
                .first()
            )

            if not customer:
                return None

            self.router.remove_hotspot_user(username=customer.phone)

            self.db.query(Payment).filter(Payment.customer_id == customer_id).delete()
            self.db.delete(customer)
            self.db.commit()

            return True