import requests

from app.config import PAYSTACK_SECRET_KEY

BASE_URL = "https://api.paystack.co"


class PaystackService:

    def charge_mpesa(self, amount, phone_number, reference):
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
                "phone": f"+{phone_number}",
                "provider": "mpesa"
            }
        }
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()

        if not data.get("status"):
            raise Exception(f"Paystack charge failed: {data}")

        return data

    def verify_transaction(self, reference):
        url = f"{BASE_URL}/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()