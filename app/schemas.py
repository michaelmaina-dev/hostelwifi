from pydantic import BaseModel

class CustomerCreate(BaseModel):
    phone: str
    name: str
    mac_address: str
    #room: str
class CustomerResponse(CustomerCreate):
    id: int

    class Config:
        from_attributes = True

class PackageCreate(BaseModel):
    name: str
    duration_value: int
    duration_unit: str
    price: int
    download_speed: str
    upload_speed: str


class PackageResponse(BaseModel):
    id: int
    name: str
    duration_seconds: int
    price: int
    download_speed: str
    upload_speed: str
    active: bool
    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    customer_id: int
    package_id: int
    mpesa_receipt: str
    status: str


class PaymentResponse(BaseModel):
    id: int
    customer_id: int
    package_id: int
    amount: float
    mpesa_receipt: str
    status: str

    class Config:
        from_attributes = True