"""
Standalone SMS notification bot for HostelWifi.

Runs as its own independent process — completely separate from the main
FastAPI app. It polls the database for newly activated payments and sends
each customer their password via SMS.

Why separate: an SMS/Africa's Talking problem (missing package, bad
credentials, API changes) should never be able to crash the actual
payment/login system. Keeping this in its own process means the two are
fully decoupled — if this bot crashes, customers can still pay and log in.

Usage:
    python3 sms_bot.py

Intended to run continuously as its own systemd service (see notes at the
bottom of this file for the service unit).
"""

import time
import os
from datetime import timedelta

from app.database import SessionLocal
from app.models import Payment
from app.services.sms_service import SMSService

STATE_FILE = "sms_bot_last_sent.txt"
POLL_INTERVAL_SECONDS = 15
KENYA_UTC_OFFSET = timedelta(hours=3)


def load_last_sent_id():
    if not os.path.exists(STATE_FILE):
        return 0
    with open(STATE_FILE, "r") as f:
        content = f.read().strip()
        return int(content) if content else 0


def save_last_sent_id(payment_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(payment_id))


def format_kenya_time(dt):
    if not dt:
        return "unknown"
    kenya_time = dt + KENYA_UTC_OFFSET
    return kenya_time.strftime("%d %b %Y, %I:%M %p")


def run_once(sms_service, last_sent_id):
    db = SessionLocal()
    try:
        new_payments = (
            db.query(Payment)
            .filter(Payment.activated == True)
            .filter(Payment.hotspot_password != None)
            .filter(Payment.id > last_sent_id)
            .order_by(Payment.id.asc())
            .all()
        )

        highest_id_seen = last_sent_id

        for payment in new_payments:
            customer = payment.customer
            if not customer or not customer.phone:
                print(f"[sms_bot] Skipping payment {payment.id}: no customer/phone")
                highest_id_seen = max(highest_id_seen, payment.id)
                continue

            expiry_str = format_kenya_time(payment.expires_at)
            message = (
                f"Shadow WiFi: Your password is {payment.hotspot_password}. "
                f"Valid until {expiry_str}. Use your phone number as username."
            )

            try:
                sms_service.send_password_sms(customer.phone, payment.hotspot_password)
                print(f"[sms_bot] Sent SMS for payment {payment.id} to {customer.phone}")
            except Exception as e:
                print(f"[sms_bot] Failed to send SMS for payment {payment.id}: {e}")
                # Don't advance past this one — retry it next cycle.
                break

            highest_id_seen = max(highest_id_seen, payment.id)

        if highest_id_seen != last_sent_id:
            save_last_sent_id(highest_id_seen)

        return highest_id_seen

    finally:
        db.close()


def main():
    print("[sms_bot] Starting SMS notification bot...")
    sms_service = SMSService()
    last_sent_id = load_last_sent_id()
    print(f"[sms_bot] Resuming from payment id {last_sent_id}")

    while True:
        try:
            last_sent_id = run_once(sms_service, last_sent_id)
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
# ExecStart=/root/hostelwifi/venv/bin/python3 /root/hostelwifi/sms_bot.py
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
