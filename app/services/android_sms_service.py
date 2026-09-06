import requests

from app.config import ANDROID_SMS_USERNAME, ANDROID_SMS_PASSWORD

ANDROID_SMS_URL = "https://api.sms-gate.app/3rdparty/v1/message"


class AndroidSMSService:

    def send_message(self, phone_number, message):
        """Send arbitrary text — used directly for admin alerts, and
        internally by send_password_sms for the customer-facing message."""
        try:
            response = requests.post(
                ANDROID_SMS_URL,
                auth=(ANDROID_SMS_USERNAME, ANDROID_SMS_PASSWORD),
                headers={"Content-Type": "application/json"},
                json={
                    "textMessage": {"text": message},
                    "phoneNumbers": [f"+{phone_number}"]
                },
                timeout=15
            )
            response.raise_for_status()

            # A successful HTTP status (raise_for_status didn't throw) means
            # the message was accepted, even if the body is empty or not
            # valid JSON — don't let a parsing quirk turn a real success
            # into a false failure.
            try:
                result = response.json()
            except ValueError:
                result = {"status": "sent", "raw_status_code": response.status_code}

            print(f"[Android SMS] Sent to {phone_number}: {result}")
            return result
        except Exception as e:
            print(f"[Android SMS] Failed to send to {phone_number}: {e}")
            return None

    def send_password_sms(self, phone_number, password, expiry_str=None):
        if expiry_str:
            message = (
                f"Shadow WiFi: Your password is {password}. "
                f"Valid until {expiry_str}. Save this message."
            )
        else:
            message = f"Shadow WiFi: Your password is {password}. Save this message."

        return self.send_message(phone_number, message)
