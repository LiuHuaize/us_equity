from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PeriodicReturn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    period_key: str = Field(alias="periodKey")
    period_start: date = Field(alias="periodStart")
    period_end: date = Field(alias="periodEnd")
    trading_days: int = Field(alias="tradingDays")
    total_return_pct: Optional[float] = Field(default=None, alias="totalReturnPct")
    compound_return_pct: Optional[float] = Field(default=None, alias="compoundReturnPct")
    volatility_pct: Optional[float] = Field(default=None, alias="volatilityPct")
    max_drawdown_pct: Optional[float] = Field(default=None, alias="maxDrawdownPct")


class ReturnSeries(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    period: str
    rows: List[PeriodicReturn]


class ReturnStats(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    window_years: int = Field(alias="windowYears")
    periods: int
    total_return_pct: Optional[float] = Field(default=None, alias="totalReturnPct")
    average_annual_return_pct: Optional[float] = Field(default=None, alias="averageAnnualReturnPct")
    max_drawdown_pct: Optional[float] = Field(default=None, alias="maxDrawdownPct")
    average_volatility_pct: Optional[float] = Field(default=None, alias="averageVolatilityPct")
    best_period_key: Optional[str] = Field(default=None, alias="bestPeriodKey")
    best_period_return_pct: Optional[float] = Field(default=None, alias="bestPeriodReturnPct")
    worst_period_key: Optional[str] = Field(default=None, alias="worstPeriodKey")
    worst_period_return_pct: Optional[float] = Field(default=None, alias="worstPeriodReturnPct")
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
