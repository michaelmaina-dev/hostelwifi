"""
Standalone SMS notification bot for HostelWifi.

Runs as its own independent process — completely separate from the main
FastAPI app. It polls the database for newly activated payments and sends
each customer their password via SMS.

Why separate: an SMS gateway problem (missing package, bad credentials,
API changes) should never be able to crash the actual payment/login
system. Keeping this in its own process means the two are fully
decoupled — if this bot crashes, customers can still pay and log in.

State tracking: each payment is tracked independently (not a single
"highest processed" cursor) so one permanently-failing number (e.g. a
malformed phone number missing a digit) can never block every other
customer's messages behind it. Failed sends are retried up to
MAX_RETRIES times, then marked as gave-up and logged for manual
follow-up — they won't be retried forever.

Usage:
    python3 sms_bot.py

Intended to run continuously as its own systemd service (see notes at the
bottom of this file for the service unit).
"""

import time
import os
import json
from datetime import timedelta

from app.database import SessionLocal
from app.models import Payment
from app.services.android_sms_service import AndroidSMSService as SMSService

STATE_FILE = "sms_bot_state.json"
POLL_INTERVAL_SECONDS = 15
KENYA_UTC_OFFSET = timedelta(hours=3)
MAX_RETRIES = 5

# --- Admin alerting ---
# When a payment permanently gives up (hits MAX_RETRIES), an SMS alert is
# sent to this number automatically, so you don't have to watch logs or
# run a report script — you just get texted the details directly.
ADMIN_PHONE_NUMBER = "254745136987"  # <-- set this to your real number

# --- Phone number overrides ---
# Some customers pay/register under one number but want the password sent
# to a different real number they actually use. Add entries here as
# "number_on_the_account": "number_to_actually_text". Checked before every
# send — if a customer's phone matches a key here, the override number is
# used instead, silently and every time (not just after N retries).
PHONE_OVERRIDES = {
    "254705938381": "254741816683",
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"sent": [], "attempts": {}, "gave_up": []}
    with open(STATE_FILE, "r") as f:
        content = f.read().strip()
        if not content:
            return {"sent": [], "attempts": {}, "gave_up": []}
        return json.loads(content)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def format_kenya_time(dt):
    if not dt:
        return "unknown"
    kenya_time = dt + KENYA_UTC_OFFSET
    return kenya_time.strftime("%d %b %Y, %I:%M %p")


def run_once(sms_service, state):
    db = SessionLocal()
    try:
        already_handled = set(state["sent"]) | set(state["gave_up"])

        candidates = (
            db.query(Payment)
            .filter(Payment.activated == True)
            .filter(Payment.hotspot_password != None)
            .order_by(Payment.id.asc())
            .all()
        )

        state_changed = False

        for payment in candidates:
            pid = payment.id
            if pid in already_handled:
                continue

            customer = payment.customer
            if not customer or not customer.phone:
                print(f"[sms_bot] Skipping payment {pid}: no customer/phone")
                state["gave_up"].append(pid)
                state_changed = True
                continue

            send_to = PHONE_OVERRIDES.get(customer.phone, customer.phone)
            if send_to != customer.phone:
                print(f"[sms_bot] Payment {pid}: overriding {customer.phone} -> {send_to}")

            expiry_str = format_kenya_time(payment.expires_at)
            result = sms_service.send_password_sms(send_to, payment.hotspot_password, expiry_str)

            if result is not None:
                print(f"[sms_bot] Sent SMS for payment {pid} to {send_to}")
                state["sent"].append(pid)
                state["attempts"].pop(str(pid), None)
                state_changed = True
                continue

            # Failed — track the attempt count for this specific payment.
            attempts = state["attempts"].get(str(pid), 0) + 1
            state["attempts"][str(pid)] = attempts
            state_changed = True

            if attempts >= MAX_RETRIES:
                print(
                    f"[sms_bot] GIVING UP on payment {pid} to {send_to} "
                    f"after {attempts} failed attempts — likely a bad/invalid "
                    f"phone number. Needs manual follow-up."
                )
                state["gave_up"].append(pid)
                state["attempts"].pop(str(pid), None)

                alert_message = (
                    f"HostelWifi SMS ALERT: payment {pid} for {send_to} "
                    f"failed {attempts}x. Password: {payment.hotspot_password}. "
                    f"Send manually."
                )
                try:
                    sms_service.send_message(ADMIN_PHONE_NUMBER, alert_message)
                except Exception as e:
                    print(f"[sms_bot] Could not send admin alert: {e}")
            else:
                print(
                    f"[sms_bot] SMS failed for payment {pid} to {send_to} "
                    f"(attempt {attempts}/{MAX_RETRIES}) — will retry next cycle"
                )
            # Deliberately no 'break' here — a failure on one payment
            # never blocks any other payment from being attempted.

        if state_changed:
            save_state(state)

        return state

    finally:
        db.close()


def main():
    print("[sms_bot] Starting SMS notification bot...")
    sms_service = SMSService()
    state = load_state()
    print(
        f"[sms_bot] Loaded state: {len(state['sent'])} sent, "
        f"{len(state['gave_up'])} gave up, "
        f"{len(state['attempts'])} pending retry"
    )

    while True:
        try:
            state = run_once(sms_service, state)
        except Exception as e:
            print(f"[sms_bot] Error in polling cycle: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()


# --- To run as its own systemd service ---
#
# /etc/systemd/system/hostelwifi-sms.service:
#
# [Unit]
# Description=HostelWifi SMS Notification Bot
# After=network.target
#
# [Service]
# WorkingDirectory=/root/hostelwifi
# ExecStart=/root/hostelwifi/venv/bin/python3 -u /root/hostelwifi/sms_bot.py
# Restart=always
# RestartSec=5
#
# [Install]
# WantedBy=multi-user.target
#
# Then:
#   systemctl daemon-reload
#   systemctl enable hostelwifi-sms
#   systemctl start hostelwifi-sms
