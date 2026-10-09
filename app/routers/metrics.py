from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BusinessMetric
from ..schemas import BusinessMetricCreate, BusinessMetricOut

router = APIRouter(prefix="/api/business-metrics", tags=["business-metrics"])


@router.get("", response_model=list[BusinessMetricOut])
def list_metrics(
    metric_name: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(BusinessMetric)
    if metric_name is not None:
        q = q.filter(BusinessMetric.metric_name == metric_name)
    if start is not None:
        q = q.filter(BusinessMetric.date >= start)
    if end is not None:
        q = q.filter(BusinessMetric.date <= end)
    return q.order_by(BusinessMetric.date.desc()).limit(limit).all()


@router.get("/names", response_model=list[str])
def metric_names(db: Session = Depends(get_db)):
    return [name for (name,) in db.query(BusinessMetric.metric_name).distinct().order_by(BusinessMetric.metric_name).all()]


@router.post("", response_model=BusinessMetricOut, status_code=201)
def create_metric(payload: BusinessMetricCreate, db: Session = Depends(get_db)):
    metric = BusinessMetric(
        date=payload.date,
        metric_name=payload.metric_name.strip(),
        value=payload.value,
        unit=payload.unit.strip(),
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric
