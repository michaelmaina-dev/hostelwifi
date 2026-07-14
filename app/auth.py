from fastapi import Header, HTTPException
from app.config import ADMIN_API_KEY


def verify_admin_key(x_api_key: str = Header(...)):
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")