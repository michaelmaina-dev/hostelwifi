import requests

from app.config import PESAPAL_CONSUMER_KEY, PESAPAL_CONSUMER_SECRET, PESAPAL_BASE_URL


class PesapalService:

    def authenticate(self):
        url = f"{PESAPAL_BASE_URL}/api/Auth/RequestToken"
        payload = {
            "consumer_key": PESAPAL_CONSUMER_KEY,
            "consumer_secret": PESAPAL_CONSUMER_SECRET
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()["token"]

    def register_ipn(self, token, callback_url):
        url = f"{PESAPAL_BASE_URL}/api/URLSetup/RegisterIPN"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        payload = {
            "url": callback_url,
            "ipn_notification_type": "GET"
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["ipn_id"]

    def submit_order(self, token, notification_id, order_id, amount, phone_number, callback_url):
        url = f"{PESAPAL_BASE_URL}/api/Transactions/SubmitOrderRequest"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        payload = {
            "id": order_id,
            "currency": "KES",
            "amount": amount,
            "description": "WiFi Payment",
            "callback_url": callback_url,
            "notification_id": notification_id,
            "billing_address": {
                "email_address": f"{phone_number}@noemail.hostelwifi.local",
                "phone_number": phone_number,
                "country_code": "KE"
            }
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_transaction_status(self, token, order_tracking_id):
        url = f"{PESAPAL_BASE_URL}/api/Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()