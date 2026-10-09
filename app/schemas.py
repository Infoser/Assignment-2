from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecordCreate(BaseModel):
    scope: int = Field(description="1 or 2 (3 accepted for reporting completeness)")
    activity: str = Field(description="Activity name, must exist in the EmissionFactors master data")
    section: str
    plant: str = "Central Steel Plant"
    quantity: float = Field(gt=0)
    unit: str
    activity_date: date = Field(description="Date the activity occurred; engine picks the factor valid on this date")

    @field_validator("scope")
    @classmethod
    def scope_valid(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("scope must be 1, 2 or 3")
        return v


class OverrideCreate(BaseModel):
    new_value_kgco2e: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    changed_by: str = Field(min_length=1, max_length=120)


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: int
    activity: str
    section: str
    plant: str
    quantity: float
    unit: str
    activity_date: date
    factor_id: int
    factor_value_used: float
    emissions_kgco2e: float
    overridden: bool
    overridden_value_kgco2e: float | None
    effective_emissions: float
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_id: int
    action: str
    old_value_kgco2e: float
    new_value_kgco2e: float
    reason: str
    changed_by: str
    changed_at: datetime


class FactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: int
    activity: str
    unit: str
    co2e_per_unit: float
    source: str
    valid_from: date
    valid_to: date | None
    version: int


class BusinessMetricCreate(BaseModel):
    date: date
    metric_name: str
    value: float = Field(ge=0)
    unit: str = "units"


class BusinessMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    metric_name: str
    value: float
    unit: str


class ScopeTotals(BaseModel):
    scope_1: float
    scope_2: float
    scope_3: float
    total: float


class YoYResponse(BaseModel):
    current_year: int
    previous_year: int
    current: ScopeTotals
    previous: ScopeTotals
    change_pct: dict[str, float | None]


class IntensityResponse(BaseModel):
    start_date: date
    end_date: date
    metric_name: str
    metric_value: float
    total_emissions_kgco2e: float
    total_emissions_tco2e: float
    intensity_kgco2e_per_unit: float
    intensity_tco2e_per_unit: float


class HotspotItem(BaseModel):
    source: str
    scope: int
    emissions_kgco2e: float
    emissions_tco2e: float
    share_pct: float


class HotspotResponse(BaseModel):
    start_date: date
    end_date: date
    total_kgco2e: float
    breakdown: list[HotspotItem]


class MonthlyItem(BaseModel):
    month: str
    scope_1: float
    scope_2: float
    scope_3: float
    total: float


class MonthlyResponse(BaseModel):
    year: int
    months: list[MonthlyItem]
