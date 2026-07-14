import base64
import requests
from datetime import datetime

from app.config import (
    MPESA_CONSUMER_KEY,
    MPESA_CONSUMER_SECRET,
    MPESA_SHORTCODE,
    MPESA_PASSKEY,
    MPESA_CALLBACK_URL
)


class MpesaService:

    def get_access_token(self):
        url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

        response = requests.get(
            url,
            auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET)
        )

        response.raise_for_status()

        data = response.json()
        return data["access_token"]

    def build_password(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        raw_string = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
        encoded = base64.b64encode(raw_string.encode()).decode()

        return encoded, timestamp

    def stk_push(self, phone_number, amount, account_reference, description):
        access_token = self.get_access_token()
        password, timestamp = self.build_password()

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "BusinessShortCode": MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": MPESA_SHORTCODE,
            "PhoneNumber": phone_number,
            "CallBackURL": MPESA_CALLBACK_URL,
            "AccountReference": account_reference,
            "TransactionDesc": description
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()