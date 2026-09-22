from sqlalchemy.orm import Session

from app.models import Customer, Package, Payment, DailyUsage
from app.services.mikrotik import MikroTikService
from datetime import datetime, timedelta, timezone, date
import secrets




def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_password(length=10):
    # Digits + uppercase letters only, no lowercase — and 0/O excluded
    # entirely since they're easy to confuse when read off a screen.
    digits = "123456789"
    uppercase = "ABCDEFGHIJKLMNPQRSTUVWXYZ"  # O removed
    characters = digits + uppercase
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

        # If this package has fair-use throttling configured, make sure its
        # throttled profile also exists on the router now, so
        # check_daily_quotas can switch a customer onto it later without
        # hitting a missing-profile error mid-day.
        if package.daily_quota_mb and package.throttle_upload and package.throttle_download:
            throttle_profile = f"throttled_{package.id}"
            throttle_rate = f"{package.throttle_upload}/{package.throttle_download}"
            self.router.ensure_profile(throttle_profile, throttle_rate, shared_users=package.shared_users)

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

    def _customers_latest_active_payment(self, customer):
        """Return the customer's most recent activated payment, used to
        find which package (and therefore which fair-use rules) currently
        applies to them."""
        return (
            self.db.query(Payment)
            .filter(Payment.customer_id == customer.id, Payment.activated == True)
            .order_by(Payment.expires_at.desc())
            .first()
        )

    def check_daily_quotas(self):
        """Fair-use enforcement: for every non-suspended customer whose
        current package defines a daily_quota_mb, poll their live router
        session(s), accumulate today's usage as a delta (so reconnects and
        polling gaps don't lose or double-count data), and switch them
        onto their package's throttled profile once they cross the quota.

        Intended to run frequently (every few minutes) via the scheduler.
        Pairs with reset_daily_throttles, which restores full speed the
        next day.

        Logs a one-line summary every run (customers checked / eligible
        for fair-use / currently connected / newly throttled), plus a
        per-customer line whenever something notable happens, so an empty
        journalctl output can never be mistaken for "this isn't running" —
        if the job runs, it always prints at least the summary line.
        """
        today = date.today()
        customers = self.db.query(Customer).filter(Customer.suspended == False).all()

        eligible_count = 0
        connected_count = 0
        newly_throttled = 0

        for customer in customers:
            latest_payment = self._customers_latest_active_payment(customer)
            if not latest_payment or not latest_payment.package:
                continue

            package = latest_payment.package
            if not package.daily_quota_mb or not package.throttle_upload or not package.throttle_download:
                continue  # this package doesn't use fair-use throttling

            eligible_count += 1

            current_session_bytes = self.router.get_total_user_bytes(customer.phone)
            if current_session_bytes is None:
                continue  # user doesn't exist on router at all — skip

            connected_count += 1

            usage_row = (
                self.db.query(DailyUsage)
                .filter(DailyUsage.customer_id == customer.id, DailyUsage.date == today)
                .first()
            )

            if not usage_row:
                # First time we've seen this customer today: record the
                # current counter as a baseline rather than counting
                # whatever they'd already used before we started watching
                # (e.g. carryover from a session spanning midnight).
                usage_row = DailyUsage(
                    customer_id=customer.id,
                    date=today,
                    bytes_used=0,
                    last_session_bytes=current_session_bytes,
                )
                self.db.add(usage_row)
                self.db.flush()
            else:
                if current_session_bytes < usage_row.last_session_bytes:
                    # Counter dropped: the session restarted (disconnect
                    # then reconnect). The new reading is fresh usage on
                    # its own, not a delta against the old counter.
                    delta = current_session_bytes
                else:
                    delta = current_session_bytes - usage_row.last_session_bytes

                usage_row.bytes_used += delta
                usage_row.last_session_bytes = current_session_bytes

            quota_bytes = package.daily_quota_mb * 1024 * 1024
            used_mb = usage_row.bytes_used / (1024 * 1024)
            quota_mb = package.daily_quota_mb

            if usage_row.bytes_used >= quota_bytes and not usage_row.throttled:
                throttle_profile = f"throttled_{package.id}"
                try:
                    self.router.set_user_profile(customer.phone, throttle_profile)
                    usage_row.throttled = True
                    newly_throttled += 1
                    print(
                        f"[billing] THROTTLED customer {customer.id} ({customer.phone}) "
                        f"on {package.name}: {used_mb:.0f}MB / {quota_mb}MB quota "
                        f"-> switched to {throttle_profile}"
                    )
                except Exception as e:
                    print(
                        f"[billing] FAILED to throttle customer {customer.id} "
                        f"({customer.phone}) on {package.name}: {e}"
                    )
            elif usage_row.throttled:
                # Already throttled earlier today — quiet on subsequent
                # polls, reset_daily_throttles handles restoring them.
                pass
            else:
                # Connected and being tracked, but not over quota yet.
                # One line per customer per poll is intentionally verbose
                # right now so usage can be watched in real time; trim
                # this once the system's been confirmed working.
                print(
                    f"[billing] tracking customer {customer.id} ({customer.phone}) "
                    f"on {package.name}: {used_mb:.0f}MB / {quota_mb}MB quota"
                )

            self.db.commit()

        print(
            f"[billing] check_daily_quotas run complete: "
            f"{len(customers)} active customers, {eligible_count} on fair-use packages, "
            f"{connected_count} currently connected, {newly_throttled} newly throttled"
        )

    def reset_daily_throttles(self):
        """Restore full package speed for anyone throttled on a previous
        day. Intended to run once daily, shortly after midnight, via the
        scheduler."""
        today = date.today()

        throttled_rows = (
            self.db.query(DailyUsage)
            .filter(DailyUsage.throttled == True, DailyUsage.date < today)
            .all()
        )

        for row in throttled_rows:
            customer = row.customer
            if not customer or customer.suspended:
                continue

            latest_payment = self._customers_latest_active_payment(customer)
            if not latest_payment or not latest_payment.package:
                continue

            package = latest_payment.package
            normal_profile = f"pkg_{package.id}"
            try:
                self.router.set_user_profile(customer.phone, normal_profile)
            except Exception as e:
                print(f"[billing] Failed to restore profile for customer {customer.id}: {e}")
