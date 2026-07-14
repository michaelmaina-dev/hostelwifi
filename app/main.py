from contextlib import asynccontextmanager
from fastapi import FastAPI

from .database import engine
from . import models

from .routers import customers
from .routers import packages
from .routers import payments
from .routers import activate_pay
from .routers import extend_period
from .routers import suspend_acc

from .scheduler import scheduler
from .routers import mpesa
from .routers import pages


models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Hostel WiFi Billing System",
    version="1.0",
    lifespan=lifespan
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(customers.router)
app.include_router(packages.router)
app.include_router(payments.router)
app.include_router(mpesa.router)
app.include_router(activate_pay.router)
app.include_router(extend_period.router)
app.include_router(suspend_acc.router)
app.include_router(pages.router)


@app.get("/")
def home():
    return {
        "message": "Hostel WiFi Backend Running"
    }

'''
from fastapi import FastAPI

from .database import engine
from . import models

from .routers import customers
from .routers import packages
from .routers import payments
from app.scheduler import scheduler

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Hostel WiFi Billing System",
    version="1.0"
)

app.include_router(customers.router)
app.include_router(packages.router)
app.include_router(payments.router)

@app.on_event("startup")
def start_scheduler():
    scheduler.start()


@app.get("/")
def home():
    return {
        "message": "Hostel WiFi Backend Running"
    }'''



