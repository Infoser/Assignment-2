"""Calculation engine: resolves the emission factor valid on a given activity date.

Historical accuracy rule: when a record is created, the engine selects the
factor revision that was in effect at the time the activity occurred
(valid_from <= activity_date <= valid_to), choosing the highest version if
several match — never simply the latest factor in the master data.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import EmissionFactor


def resolve_factor(db: Session, activity: str, activity_date: date) -> EmissionFactor:
    factor = (
        db.query(EmissionFactor)
        .filter(
            EmissionFactor.activity == activity,
            EmissionFactor.valid_from <= activity_date,
            (EmissionFactor.valid_to.is_(None)) | (EmissionFactor.valid_to >= activity_date),
        )
        .order_by(EmissionFactor.version.desc())
        .first()
    )
    if factor is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No emission factor is valid for activity '{activity}' on {activity_date}. "
                f"Known activities: use GET /api/factors to inspect the master data."
            ),
        )
    return factor


def compute_emissions(quantity: float, factor: EmissionFactor) -> float:
    """Activity Data x Emission Factor = GHG Emissions (kgCO2e)."""
    return quantity * factor.co2e_per_unit
