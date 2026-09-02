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

        # If they still have unexpired time from an earlier payment, add this
        # package's duration on top of that. Otherwise, start fresh from now.
        now = utc_now()
        previous_expiry = customer.payments and max(
            (p.expires_at for p in customer.payments
             if p.activated and p.expires_at and p.expires_at > now and p.id != payment.id),
            default=None
        )

        base_time = previous_expiry if previous_expiry else now
        payment.expires_at = base_time + timedelta(seconds=package.duration_seconds)

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

    def extend_customer(self, payment_id: int, extra_seconds: int = None):
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

        # Use a custom bonus duration if given, otherwise default to a full
        # extra package length (original behavior).
        seconds_to_add = extra_seconds if extra_seconds is not None else package.duration_seconds
        payment.expires_at = payment.expires_at + timedelta(seconds=seconds_to_add)

        # If the customer is currently suspended on the router, re-sync them
        # so the extension actually takes effect there too, not just in the DB.
        customer = payment.customer
        if customer and customer.suspended:
            if not payment.hotspot_password:
                # Don't push a None/empty password to the router — that would
                # overwrite their real password with garbage. Extend the DB
                # expiry, but leave the re-enable to be handled manually
                # (or by a fresh activate_payment call with a real password).
                self.db.commit()
                return payment

            profile_name = f"pkg_{package.id}"
            self.router.create_hotspot_user(
                username=customer.phone,
                password=payment.hotspot_password,
                profile=profile_name
            )
            customer.suspended = False

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
