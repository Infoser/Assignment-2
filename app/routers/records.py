from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, EmissionFactor, EmissionRecord
from ..schemas import AuditLogOut, FactorOut, OverrideCreate, RecordCreate, RecordOut
from .engine import compute_emissions, resolve_factor

router = APIRouter(prefix="/api", tags=["records"])


@router.post("/records", response_model=RecordOut, status_code=201)
def create_record(payload: RecordCreate, db: Session = Depends(get_db)):
    """Create a Scope 1/2 (or 3) emission record.

    The engine resolves the emission factor that was valid on the activity
    date (historical accuracy) and computes:
        quantity x factor = emissions (kgCO2e)
    """
    factor = resolve_factor(db, payload.activity.strip(), payload.activity_date)
    record = EmissionRecord(
        scope=payload.scope,
        activity=factor.activity,
        section=payload.section.strip(),
        plant=payload.plant.strip(),
        quantity=payload.quantity,
        unit=factor.unit,
        activity_date=payload.activity_date,
        factor_id=factor.id,
        factor_value_used=factor.co2e_per_unit,
        emissions_kgco2e=compute_emissions(payload.quantity, factor),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/records", response_model=list[RecordOut])
def list_records(
    scope: int | None = Query(default=None, ge=1, le=3),
    start: date | None = None,
    end: date | None = None,
    activity: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(EmissionRecord)
    if scope is not None:
        q = q.filter(EmissionRecord.scope == scope)
    if start is not None:
        q = q.filter(EmissionRecord.activity_date >= start)
    if end is not None:
        q = q.filter(EmissionRecord.activity_date <= end)
    if activity is not None:
        q = q.filter(EmissionRecord.activity.ilike(f"%{activity}%"))
    return q.order_by(EmissionRecord.activity_date.desc(), EmissionRecord.id.desc()).offset(offset).limit(limit).all()


@router.patch("/records/{record_id}/override", response_model=RecordOut)
def override_record(record_id: int, payload: OverrideCreate, db: Session = Depends(get_db)):
    """Manually override the calculated emissions of a record.

    Every override is written to the AuditLog with the old value, new value,
    reason and author, forming a complete audit trail.
    """
    record = db.get(EmissionRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    old_value = record.effective_emissions
    record.overridden = True
    record.overridden_value_kgco2e = payload.new_value_kgco2e
    db.add(AuditLog(
        record_id=record.id,
        action="OVERRIDE",
        old_value_kgco2e=old_value,
        new_value_kgco2e=payload.new_value_kgco2e,
        reason=payload.reason.strip(),
        changed_by=payload.changed_by.strip(),
    ))
    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}/override", response_model=RecordOut)
def revert_override(record_id: int, db: Session = Depends(get_db)):
    """Revert a manual override back to the engine-calculated value (audit logged)."""
    record = db.get(EmissionRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    if not record.overridden:
        raise HTTPException(status_code=409, detail=f"Record {record_id} is not overridden")
    old_value = record.effective_emissions
    record.overridden = False
    record.overridden_value_kgco2e = None
    db.add(AuditLog(
        record_id=record.id,
        action="REVERT",
        old_value_kgco2e=old_value,
        new_value_kgco2e=record.emissions_kgco2e,
        reason="Manual override reverted to engine-calculated value",
        changed_by="system",
    ))
    db.commit()
    db.refresh(record)
    return record


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(record_id: int | None = None, limit: int = Query(default=100, le=500), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if record_id is not None:
        q = q.filter(AuditLog.record_id == record_id)
    return q.order_by(AuditLog.changed_at.desc(), AuditLog.id.desc()).limit(limit).all()


@router.get("/factors", response_model=list[FactorOut])
def list_factors(
    scope: int | None = Query(default=None, ge=1, le=3),
    activity: str | None = None,
    valid_on: date | None = Query(default=None, description="Only factors valid on this date"),
    db: Session = Depends(get_db),
):
    q = db.query(EmissionFactor)
    if scope is not None:
        q = q.filter(EmissionFactor.scope == scope)
    if activity is not None:
        q = q.filter(EmissionFactor.activity.ilike(f"%{activity}%"))
    if valid_on is not None:
        q = q.filter(
            EmissionFactor.valid_from <= valid_on,
            (EmissionFactor.valid_to.is_(None)) | (EmissionFactor.valid_to >= valid_on),
        )
    return q.order_by(EmissionFactor.activity, EmissionFactor.valid_from).all()


@router.get("/factors/resolve", response_model=FactorOut)
def resolve_factor_api(activity: str, on: date, db: Session = Depends(get_db)):
    """Demonstrates historical accuracy: returns the factor the engine would use for a date."""
    return resolve_factor(db, activity.strip(), on)
