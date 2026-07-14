from contextlib import asynccontextmanager
from fastapi import FastAPI

from .database import engine
from . import models

from .routers import customers
from .routers import packages
from .routers import payments
from .routers import acitivate_pay
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

app.include_router(customers.router)
app.include_router(packages.router)
app.include_router(payments.router)
app.include_router(mpesa.router)
app.include_router(acitivate_pay.router)
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



