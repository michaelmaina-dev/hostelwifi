import requests

from app.config import PAYSTACK_SECRET_KEY

BASE_URL = "https://api.paystack.co"


class PaystackService:

    def charge_mpesa(self, amount, phone_number, reference):
        # phone_number arrives as 254XXXXXXXXX from the router's normalization
        # Paystack's mobile_money field wants local format: 0XXXXXXXXX
        local_phone = "0" + phone_number[3:] if phone_number.startswith("254") else phone_number

        url = f"{BASE_URL}/charge"
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "email": f"{phone_number}@shadownet.fyi",
            "amount": int(amount * 100),
            "currency": "KES",
            "reference": reference,
            "mobile_money": {
                "phone": local_phone,
                "provider": "mpesa"
            }
        }
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        data = response.json()

        if not data.get("status"):
            raise Exception(f"Paystack charge failed: {data}")

        return data

    def verify_transaction(self, reference):
        url = f"{BASE_URL}/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()