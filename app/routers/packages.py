from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(
    prefix="/packages",
    tags=["Packages"]
)


UNIT_TO_SECONDS = {
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
    "month": 2592000, "months": 2592000,  # approximated as 30 days
}


@router.post("", response_model=schemas.PackageResponse)
def create_package(
    package: schemas.PackageCreate,
    db: Session = Depends(get_db)
):
    unit = package.duration_unit.lower()

    if unit not in UNIT_TO_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid duration_unit '{package.duration_unit}'. Use minutes, hours, days, weeks, or months."
        )

    duration_seconds = package.duration_value * UNIT_TO_SECONDS[unit]

    db_package = models.Package(
        name=package.name,
        duration_seconds=duration_seconds,
        price=package.price,
        download_speed=package.download_speed,
        upload_speed=package.upload_speed
    )

    db.add(db_package)
    db.commit()
    db.refresh(db_package)

    return db_package


@router.get("")
def get_packages(db: Session = Depends(get_db)):
    return db.query(models.Package).all()
'''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(
    prefix="/packages",
    tags=["Packages"]
)


@router.post("", response_model=schemas.PackageResponse)
def create_package(
    package: schemas.PackageCreate,
    db: Session = Depends(get_db)
):

    db_package = models.Package(**package.model_dump())

    db.add(db_package)
    db.commit()
    db.refresh(db_package)

    return db_package


@router.get("")
def get_packages(db: Session = Depends(get_db)):
    return db.query(models.Package).all()'''