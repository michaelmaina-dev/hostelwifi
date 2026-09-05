import requests

from app.config import ANDROID_SMS_USERNAME, ANDROID_SMS_PASSWORD

ANDROID_SMS_URL = "https://api.sms-gate.app/3rdparty/v1/message"


class AndroidSMSService:

    def send_password_sms(self, phone_number, password):
        message = f"Shadow WiFi: Your password is {password}. Save this message. Use your phone number as username."

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
            result = response.json()
            print(f"[Android SMS] Sent to {phone_number}: {result}")
            return result
        except Exception as e:
            print(f"[Android SMS] Failed to send to {phone_number}: {e}")
            return None
