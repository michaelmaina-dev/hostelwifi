from contextlib import asynccontextmanager
#from fastapi import FastAPI
import secrets
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from .config import ADMIN_API_KEY
from fastapi.staticfiles import StaticFiles
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
from .routers import admin
from .routers import pesapal_pay
from .routers import paystack_pay



models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Hostel WiFi Billing System",
    version="1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
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
app.include_router(admin.router)
app.include_router(pesapal_pay.router)
app.include_router(paystack_pay.router)
@app.get("/")
def home():
    return {
        "message": "Hostel WiFi Backend Running"
    }

docs_security = HTTPBasic()


def docs_login(credentials: HTTPBasicCredentials = Depends(docs_security)):
    # Username is ignored; the password must be the admin API key.
    if not secrets.compare_digest(credentials.password.encode("utf-8"), ADMIN_API_KEY.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/docs", include_in_schema=False, dependencies=[Depends(docs_login)])
def docs_page():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Hostel WiFi - API docs")


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(docs_login)])
def docs_schema():
    return app.openapi()
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



