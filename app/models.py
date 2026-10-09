from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class EmissionFactor(Base):
    """Versioned master data for emission factors.

    A factor is valid for a given activity date when:
        valid_from <= activity_date AND (valid_to IS NULL OR valid_to >= activity_date)
    The calculation engine resolves the factor row that was in effect on the
    activity date (historical accuracy), not simply the latest version.
    """

    __tablename__ = "emission_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[int] = mapped_column(Integer, nullable=False)
    activity: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    co2e_per_unit: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_factors_activity_validity", "activity", "valid_from", "valid_to"),
    )


class EmissionRecord(Base):
    """One recorded emission event (Scope 1, 2 or 3).

    Stores the resolved factor snapshot alongside the computed result so the
    record remains reproducible even if master data changes later.
    """

    __tablename__ = "emission_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[int] = mapped_column(Integer, nullable=False)
    activity: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    section: Mapped[str] = mapped_column(String(120), nullable=False)
    plant: Mapped[str] = mapped_column(String(120), nullable=False, default="Central Steel Plant")
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    factor_id: Mapped[int] = mapped_column(ForeignKey("emission_factors.id"), nullable=False)
    factor_value_used: Mapped[float] = mapped_column(Float, nullable=False)
    emissions_kgco2e: Mapped[float] = mapped_column(Float, nullable=False)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overridden_value_kgco2e: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    factor = relationship("EmissionFactor")

    @property
    def effective_emissions(self) -> float:
        return self.overridden_value_kgco2e if self.overridden else self.emissions_kgco2e


class AuditLog(Base):
    """Trail of every manual override (and revert) on emission records."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("emission_records.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    old_value_kgco2e: Mapped[float] = mapped_column(Float, nullable=False)
    new_value_kgco2e: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class BusinessMetric(Base):
    """Key business metrics over time, used for intensity denominators."""

    __tablename__ = "business_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")
