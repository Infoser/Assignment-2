from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, extract, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BusinessMetric, EmissionRecord
from ..schemas import (
    HotspotItem,
    HotspotResponse,
    IntensityResponse,
    MonthlyItem,
    MonthlyResponse,
    ScopeTotals,
    YoYResponse,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

effective = case(
    (EmissionRecord.overridden.is_(True), EmissionRecord.overridden_value_kgco2e),
    else_=EmissionRecord.emissions_kgco2e,
)


def latest_activity_date(db: Session) -> date:
    return db.query(func.max(EmissionRecord.activity_date)).scalar()


def scope_totals(db: Session, start: date, end: date, scope: int | None = None) -> ScopeTotals:
    q = db.query(EmissionRecord.scope, func.sum(effective)).filter(
        EmissionRecord.activity_date >= start,
        EmissionRecord.activity_date <= end,
    )
    if scope is not None:
        q = q.filter(EmissionRecord.scope == scope)
    sums = {s: float(total or 0) for s, total in q.group_by(EmissionRecord.scope).all()}
    return ScopeTotals(
        scope_1=sums.get(1, 0.0),
        scope_2=sums.get(2, 0.0),
        scope_3=sums.get(3, 0.0),
        total=sum(sums.values()),
    )


@router.get("/yoy", response_model=YoYResponse)
def year_over_year(
    year: int | None = Query(default=None, description="Defaults to the latest year present in the data"),
    db: Session = Depends(get_db),
):
    """Total emissions by Scope for the current and previous year (override-aware)."""
    current_year = year or latest_activity_date(db).year
    previous_year = current_year - 1
    current = scope_totals(db, date(current_year, 1, 1), date(current_year, 12, 31))
    previous = scope_totals(db, date(previous_year, 1, 1), date(previous_year, 12, 31))

    def pct(cur: float, prev: float) -> float | None:
        return round((cur - prev) / prev * 100.0, 2) if prev else None

    return YoYResponse(
        current_year=current_year,
        previous_year=previous_year,
        current=current,
        previous=previous,
        change_pct={
            "scope_1": pct(current.scope_1, previous.scope_1),
            "scope_2": pct(current.scope_2, previous.scope_2),
            "scope_3": pct(current.scope_3, previous.scope_3),
            "total": pct(current.total, previous.total),
        },
    )


@router.get("/intensity", response_model=IntensityResponse)
def emission_intensity(
    start: date | None = None,
    end: date | None = None,
    metric: str = Query(default="Tons of Steel Produced", description="BusinessMetric name used as denominator"),
    scope: int | None = Query(default=None, ge=1, le=3),
    db: Session = Depends(get_db),
):
    """Emission Intensity: kgCO2e per unit of production for a given period."""
    end = end or latest_activity_date(db)
    start = start or date(end.year, 1, 1)
    q = db.query(func.sum(effective)).filter(
        EmissionRecord.activity_date >= start,
        EmissionRecord.activity_date <= end,
    )
    if scope is not None:
        q = q.filter(EmissionRecord.scope == scope)
    total_kgco2e = float(q.scalar() or 0.0)
    metric_value = float(
        db.query(func.sum(BusinessMetric.value))
        .filter(
            BusinessMetric.metric_name == metric,
            BusinessMetric.date >= start,
            BusinessMetric.date <= end,
        )
        .scalar() or 0.0
    )
    intensity_kg = round(total_kgco2e / metric_value, 4) if metric_value else None
    return IntensityResponse(
        start_date=start,
        end_date=end,
        metric_name=metric,
        metric_value=metric_value,
        total_emissions_kgco2e=total_kgco2e,
        total_emissions_tco2e=round(total_kgco2e / 1000.0, 2),
        intensity_kgco2e_per_unit=intensity_kg,
        intensity_tco2e_per_unit=round(intensity_kg / 1000.0, 6) if intensity_kg is not None else None,
    )


@router.get("/hotspot", response_model=HotspotResponse)
def emission_hotspot(
    start: date | None = None,
    end: date | None = None,
    scope: int | None = Query(default=None, ge=1, le=3),
    db: Session = Depends(get_db),
):
    """Breakdown of total emissions by source to identify the largest contributors."""
    end = end or latest_activity_date(db)
    start = start or date(end.year, 1, 1)
    q = (
        db.query(EmissionRecord.scope, EmissionRecord.activity, func.sum(effective))
        .filter(
            EmissionRecord.activity_date >= start,
            EmissionRecord.activity_date <= end,
        )
        .group_by(EmissionRecord.scope, EmissionRecord.activity)
    )
    if scope is not None:
        q = q.filter(EmissionRecord.scope == scope)
    rows = [(s, a, float(total or 0)) for s, a, total in q.all()]
    total = sum(e for _, _, e in rows) or 1.0
    breakdown = sorted(
        (
            HotspotItem(
                source=a,
                scope=s,
                emissions_kgco2e=round(e, 2),
                emissions_tco2e=round(e / 1000.0, 2),
                share_pct=round(e / total * 100.0, 2),
            )
            for s, a, e in rows
        ),
        key=lambda item: item.emissions_kgco2e,
        reverse=True,
    )
    return HotspotResponse(
        start_date=start,
        end_date=end,
        total_kgco2e=round(sum(e for _, _, e in rows), 2),
        breakdown=breakdown,
    )


@router.get("/monthly", response_model=MonthlyResponse)
def monthly_trend(
    year: int | None = Query(default=None, description="Defaults to the latest year present in the data"),
    scope: int | None = Query(default=None, ge=1, le=3),
    db: Session = Depends(get_db),
):
    """Total emissions per month for the given year (trend line)."""
    y = year or latest_activity_date(db).year
    if db.get_bind().dialect.name == "sqlite":
        month_expr = func.strftime("%Y-%m", EmissionRecord.activity_date)
    else:
        month_expr = func.to_char(EmissionRecord.activity_date, "YYYY-MM")
    q = (
        db.query(month_expr, EmissionRecord.scope, func.sum(effective))
        .filter(extract("year", EmissionRecord.activity_date) == y)
        .group_by(month_expr, EmissionRecord.scope)
    )
    if scope is not None:
        q = q.filter(EmissionRecord.scope == scope)
    data: dict[str, dict[int, float]] = {}
    for month, s, total in q.all():
        data.setdefault(month, {})[s] = float(total or 0)
    months = [
        MonthlyItem(
            month=f"{y}-{m:02d}",
            scope_1=data.get(f"{y}-{m:02d}", {}).get(1, 0.0),
            scope_2=data.get(f"{y}-{m:02d}", {}).get(2, 0.0),
            scope_3=data.get(f"{y}-{m:02d}", {}).get(3, 0.0),
            total=sum(data.get(f"{y}-{m:02d}", {}).values()),
        )
        for m in range(1, 13)
    ]
    return MonthlyResponse(year=y, months=months)
