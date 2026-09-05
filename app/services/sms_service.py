import africastalking

from app.config import AT_USERNAME, AT_API_KEY


class SMSService:

    def __init__(self):
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        self.sms = africastalking.SMS

    def send_password_sms(self, phone_number, password):
        message = f"Shadow WiFi: Your password is {password}. Save this message. Use your phone number as username."
        recipients = [f"+{phone_number}"]

        try:
            response = self.sms.send(message, recipients)
            return response
        except Exception as e:
            print(f"[SMS] Failed to send to {phone_number}: {e}")
            return None