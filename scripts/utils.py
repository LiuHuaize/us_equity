from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence, Tuple


LOGGER = logging.getLogger(__name__)


def parse_split_ratio(raw_value: Any) -> Optional[Decimal]:
    """
    Convert EODHD split ratio strings like '4:1' or '1/2' into Decimal.
    Returns None if value cannot be parsed.
    """
    if raw_value is None:
        return None

    if isinstance(raw_value, (int, float, Decimal)):
        try:
            return Decimal(str(raw_value))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to convert split ratio numeric value %s: %s", raw_value, exc)
            return None

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        separators = [":", "/", " "]
        for sep in separators:
            if sep in text:
                parts = [p for p in text.split(sep) if p]
                if len(parts) == 2:
                    try:
                        numerator = Decimal(parts[0])
                        denominator = Decimal(parts[1])
                        if denominator == 0:
                            return None
                        return numerator / denominator
                    except Exception as exc:  # pragma: no cover
                        LOGGER.warning("Unable to parse split ratio '%s': %s", text, exc)
                        return None
        try:
            return Decimal(text)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Unable to parse split ratio '%s': %s", text, exc)
            return None
    LOGGER.warning("Unsupported split ratio type: %s (%s)", raw_value, type(raw_value))
    return None


def _extract_latest_from_collection(collection: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    try:
        sorted_items = sorted(
            (
                (int(item["date"]) if item["date"].isdigit() else item["date"], item)
                for item in collection.values()
                if isinstance(item, dict) and item.get("shares")
            ),
            reverse=True,
        )
        if sorted_items:
            return sorted_items[0][1]
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to extract latest shares from collection: %s", exc)
    return None


def derive_shares_from_payload(payload: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Derive SharesOutstanding and SharesFloat numbers.
    Priority:
      1. `SharesStats` fields if present.
      2. `outstandingShares` annual/quarterly latest entries (`shares` field).
    Returns tuple (shares_outstanding, shares_float) as Decimal or None.
    """
    shares_stats = payload.get("SharesStats") or {}
    outstanding = payload.get("outstandingShares") or {}

    outstanding_value = shares_stats.get("SharesOutstanding")
    float_value = shares_stats.get("SharesFloat")

    def to_decimal(value: Any) -> Optional[Decimal]:
        if value in (None, "", "0"):
            return None
        try:
            return Decimal(str(value))
        except Exception:  # pragma: no cover
            return None

    shares_outstanding = to_decimal(outstanding_value)
    shares_float = to_decimal(float_value)

    if shares_outstanding is None and outstanding:
        annual = outstanding.get("annual") or {}
        latest = _extract_latest_from_collection(annual)
        if not latest:
            quarterly = outstanding.get("quarterly") or {}
            latest = _extract_latest_from_collection(quarterly)
        if latest and latest.get("shares"):
            shares_outstanding = to_decimal(latest["shares"])
        if latest and latest.get("sharesMln") and shares_outstanding is None:
            shares_outstanding = to_decimal(Decimal(latest["sharesMln"]) * Decimal("1_000_000"))

    if shares_float is None:
        # As a fallback, assume float equals outstanding when no dedicated value.
        shares_float = shares_outstanding

    return shares_outstanding, shares_float


def normalize_sector_industry(general: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    sector = general.get("Sector") or general.get("GicSector")
    industry = general.get("Industry") or general.get("GicIndustry")
    if sector and isinstance(sector, str):
        sector = sector.strip()
    if industry and isinstance(industry, str):
        industry = industry.strip()
    return sector or None, industry or None


def canonical_symbol(request_symbol: Optional[str], general: Dict[str, Any]) -> str:
    primary = general.get("PrimaryTicker") if isinstance(general, dict) else None
    exchange = general.get("Exchange") if isinstance(general, dict) else None
    code = general.get("Code") if isinstance(general, dict) else None

    if primary and "." in primary:
        return primary

    if request_symbol and "." in request_symbol:
        return request_symbol

    base = primary or code or (request_symbol or "")
    suffix = "US"
    if exchange:
        ex = exchange.upper()
        us_aliases = {"NASDAQ", "NYSE", "AMEX", "US", "NYSE ARCA", "ARCA", "NYSE MKT"}
        if ex not in us_aliases:
            suffix = ex
    return f"{base}.{suffix}" if base else f"UNKNOWN.{suffix}"
