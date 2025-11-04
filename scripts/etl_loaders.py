from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from psycopg2.extras import execute_values

from .utils import (
    canonical_symbol,
    derive_shares_from_payload,
    normalize_sector_industry,
    parse_split_ratio,
)


LOGGER = logging.getLogger(__name__)


def upsert_symbol(cur, symbol: str, payload: Dict[str, Any]) -> str:
    general = payload.get("General", {})
    sector, industry = normalize_sector_industry(general)
    stored_symbol = canonical_symbol(symbol, general)
    cur.execute(
        """
        INSERT INTO dim_symbol (symbol, name, exchange, asset_type, sector, industry, is_active, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,true,now())
        ON CONFLICT (symbol)
        DO UPDATE SET name = EXCLUDED.name,
                      exchange = EXCLUDED.exchange,
                      asset_type = EXCLUDED.asset_type,
                      sector = EXCLUDED.sector,
                      industry = EXCLUDED.industry,
                      updated_at = now();
        """,
        (
            stored_symbol,
            general.get("Name"),
            general.get("Exchange"),
            general.get("Type"),
            sector,
            industry,
        ),
    )
    return stored_symbol


def upsert_fundamentals(cur, symbol: str, payload: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    general = payload.get("General", {})
    highlights = payload.get("Highlights", {})
    valuation = payload.get("Valuation", {})

    shares_outstanding, shares_float = derive_shares_from_payload(payload)

    updated_at_raw = general.get("UpdatedAt")
    if updated_at_raw:
        try:
            updated_at_dt = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
        except ValueError:
            updated_at_dt = datetime.now(timezone.utc)
    else:
        updated_at_dt = datetime.now(timezone.utc)

    cur.execute(
        """
        INSERT INTO stg_fundamentals (
            symbol, "FiscalYearEnd", "SharesOutstanding", "SharesFloat", "MarketCapitalization",
            "PERatio", "PriceBookMRQ", "PriceSalesTTM", "DividendYield", "DividendShare",
            "UpdatedAt", "Payload"
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (symbol, "UpdatedAt") DO NOTHING;
        """,
        (
            symbol,
            general.get("FiscalYearEnd"),
            shares_outstanding,
            shares_float,
            highlights.get("MarketCapitalization"),
            highlights.get("PERatio"),
            valuation.get("PriceBookMRQ"),
            valuation.get("PriceSalesTTM"),
            highlights.get("DividendYield"),
            highlights.get("DividendShare"),
            updated_at_dt,
            json.dumps(payload),
        ),
    )

    return shares_outstanding, shares_float


def upsert_eod_quotes(cur, symbol: str, rows: Sequence[Dict[str, Any]]) -> None:
    values: List[Tuple] = []
    now_ts = datetime.now(timezone.utc)
    for row in rows:
        values.append(
            (
                symbol,
                row.get("date"),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("adjusted_close"),
                row.get("volume"),
                now_ts,
            )
        )
    if not values:
        return
    execute_values(
        cur,
        """
        INSERT INTO stg_eod_quotes (symbol, date, open, high, low, close, adjusted_close, volume, updated_at)
        VALUES %s
        ON CONFLICT (symbol, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume = EXCLUDED.volume,
            updated_at = now();
        """,
        values,
    )


def upsert_dividends(cur, symbol: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    now_ts = datetime.now(timezone.utc)
    execute_values(
        cur,
        """
        INSERT INTO fact_corporate_actions (symbol, action_date, action_type, value, currency, source_payload, updated_at)
        VALUES %s
        ON CONFLICT (symbol, action_date, action_type) DO UPDATE SET
            value = EXCLUDED.value,
            currency = EXCLUDED.currency,
            source_payload = EXCLUDED.source_payload,
            updated_at = now();
        """,
        [
            (
                symbol,
                row.get("date"),
                "dividend",
                row.get("value"),
                row.get("currency"),
                json.dumps(row),
                now_ts,
            )
            for row in rows
        ],
    )


def upsert_splits(cur, symbol: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return

    prepared: List[Tuple] = []
    now_ts = datetime.now(timezone.utc)
    for row in rows:
        ratio = parse_split_ratio(row.get("ratio") or row.get("split") or row.get("value"))
        prepared.append(
            (
                symbol,
                row.get("date"),
                "split",
                ratio,
                row.get("to_symbol") or row.get("description"),
                json.dumps(row),
                now_ts,
            )
        )

    execute_values(
        cur,
        """
        INSERT INTO fact_corporate_actions (symbol, action_date, action_type, value, description, source_payload, updated_at)
        VALUES %s
        ON CONFLICT (symbol, action_date, action_type) DO UPDATE SET
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            source_payload = EXCLUDED.source_payload,
            updated_at = now();
        """,
        prepared,
    )


def refresh_mart_daily_quotes(cur, symbols: Sequence[str], start_date: str, end_date: str) -> None:
    if not symbols:
        return
    cur.execute(
        """
        WITH latest_fund AS (
            SELECT symbol,
                   "SharesOutstanding",
                   "SharesFloat",
                   "PERatio",
                   "PriceBookMRQ",
                   "PriceSalesTTM",
                   "DividendYield",
                   "DividendShare",
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY "UpdatedAt" DESC) AS rn
            FROM stg_fundamentals
            WHERE symbol = ANY(%s)
        ),
        fund AS (
            SELECT symbol,
                   "SharesOutstanding",
                   "SharesFloat",
                   "PERatio",
                   "PriceBookMRQ",
                   "PriceSalesTTM",
                   "DividendYield",
                   "DividendShare"
            FROM latest_fund WHERE rn = 1
        ),
        daily AS (
            SELECT q.symbol,
                   q.date AS trade_date,
                   q.open,
                   q.high,
                   q.low,
                   q.close,
                   q.adjusted_close,
                   q.volume,
                   COALESCE(div.value, 0) AS dividend,
                   COALESCE(split.value, 1) AS split_factor,
                   LAG(q.close) OVER (PARTITION BY q.symbol ORDER BY q.date) AS pre_close,
                   AVG(q.volume) OVER (PARTITION BY q.symbol ORDER BY q.date ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_volume_5,
                   f."SharesOutstanding",
                   f."SharesFloat",
                   f."PERatio",
                   f."PriceBookMRQ",
                   f."PriceSalesTTM",
                   f."DividendYield",
                   f."DividendShare"
            FROM stg_eod_quotes q
            LEFT JOIN fact_corporate_actions div
              ON div.symbol = q.symbol
             AND div.action_date = q.date
             AND div.action_type = 'dividend'
            LEFT JOIN fact_corporate_actions split
              ON split.symbol = q.symbol
             AND split.action_date = q.date
             AND split.action_type = 'split'
            LEFT JOIN fund f ON f.symbol = q.symbol
            WHERE q.symbol = ANY(%s)
              AND q.date BETWEEN %s AND %s
        )
        INSERT INTO mart_daily_quotes (
            symbol, trade_date, open, high, low, close, adjusted_close, volume,
            dividend, split_factor, pre_close, change_amt, pct_chg, amount,
            turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm,
            dv_ratio, dv_ttm, total_share, free_share, total_mv, circ_mv,
            pct_chg_5d, pct_chg_10d, pct_chg_20d, pct_chg_60d,
            created_at, updated_at
        )
        SELECT
            d.symbol,
            d.trade_date,
            d.open,
            d.high,
            d.low,
            d.close,
            d.adjusted_close,
            d.volume,
            d.dividend,
            d.split_factor,
            d.pre_close,
            CASE WHEN d.pre_close IS NOT NULL THEN d.close - d.pre_close ELSE NULL END AS change_amt,
            CASE WHEN d.pre_close IS NOT NULL AND d.pre_close <> 0 THEN (d.close - d.pre_close)/d.pre_close ELSE NULL END AS pct_chg,
            CASE WHEN d.volume IS NOT NULL AND d.close IS NOT NULL THEN d.volume * d.close ELSE NULL END AS amount,
            CASE WHEN d."SharesOutstanding" IS NOT NULL AND d."SharesOutstanding" <> 0 THEN d.volume::numeric/d."SharesOutstanding" ELSE NULL END AS turnover_rate,
            CASE WHEN d."SharesFloat" IS NOT NULL AND d."SharesFloat" <> 0 THEN d.volume::numeric/d."SharesFloat" ELSE NULL END AS turnover_rate_f,
            CASE WHEN d.avg_volume_5 IS NOT NULL AND d.avg_volume_5 <> 0 THEN d.volume::numeric / d.avg_volume_5 ELSE NULL END AS volume_ratio,
            d."PERatio" AS pe,
            d."PERatio" AS pe_ttm,
            d."PriceBookMRQ" AS pb,
            d."PriceSalesTTM" AS ps,
            d."PriceSalesTTM" AS ps_ttm,
            d."DividendYield" AS dv_ratio,
            d."DividendShare" AS dv_ttm,
            d."SharesOutstanding" AS total_share,
            d."SharesFloat" AS free_share,
            CASE WHEN d."SharesOutstanding" IS NOT NULL THEN d.close * d."SharesOutstanding" ELSE NULL END AS total_mv,
            CASE WHEN d."SharesFloat" IS NOT NULL THEN d.close * d."SharesFloat" ELSE NULL END AS circ_mv,
            CASE WHEN LAG(d.adjusted_close,5) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) IS NOT NULL
                   AND LAG(d.adjusted_close,5) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) <> 0
                   THEN d.adjusted_close / LAG(d.adjusted_close,5) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) - 1 ELSE NULL END AS pct_chg_5d,
            CASE WHEN LAG(d.adjusted_close,10) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) IS NOT NULL
                   AND LAG(d.adjusted_close,10) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) <> 0
                   THEN d.adjusted_close / LAG(d.adjusted_close,10) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) - 1 ELSE NULL END AS pct_chg_10d,
            CASE WHEN LAG(d.adjusted_close,20) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) IS NOT NULL
                   AND LAG(d.adjusted_close,20) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) <> 0
                   THEN d.adjusted_close / LAG(d.adjusted_close,20) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) - 1 ELSE NULL END AS pct_chg_20d,
            CASE WHEN LAG(d.adjusted_close,60) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) IS NOT NULL
                   AND LAG(d.adjusted_close,60) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) <> 0
                   THEN d.adjusted_close / LAG(d.adjusted_close,60) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) - 1 ELSE NULL END AS pct_chg_60d,
            now(),
            now()
        FROM daily d
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
            open=EXCLUDED.open,
            high=EXCLUDED.high,
            low=EXCLUDED.low,
            close=EXCLUDED.close,
            adjusted_close=EXCLUDED.adjusted_close,
            volume=EXCLUDED.volume,
            dividend=EXCLUDED.dividend,
            split_factor=EXCLUDED.split_factor,
            pre_close=EXCLUDED.pre_close,
            change_amt=EXCLUDED.change_amt,
            pct_chg=EXCLUDED.pct_chg,
            amount=EXCLUDED.amount,
            turnover_rate=EXCLUDED.turnover_rate,
            turnover_rate_f=EXCLUDED.turnover_rate_f,
            volume_ratio=EXCLUDED.volume_ratio,
            pe=EXCLUDED.pe,
            pe_ttm=EXCLUDED.pe_ttm,
            pb=EXCLUDED.pb,
            ps=EXCLUDED.ps,
            ps_ttm=EXCLUDED.ps_ttm,
            dv_ratio=EXCLUDED.dv_ratio,
            dv_ttm=EXCLUDED.dv_ttm,
            total_share=EXCLUDED.total_share,
            free_share=EXCLUDED.free_share,
            total_mv=EXCLUDED.total_mv,
            circ_mv=EXCLUDED.circ_mv,
            pct_chg_5d=EXCLUDED.pct_chg_5d,
            pct_chg_10d=EXCLUDED.pct_chg_10d,
            pct_chg_20d=EXCLUDED.pct_chg_20d,
            pct_chg_60d=EXCLUDED.pct_chg_60d,
            updated_at=now();
        """,
        (list(symbols), list(symbols), start_date, end_date),
    )


def log_null_metrics(cur, symbols: Sequence[str]) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT symbol,
               COUNT(*) AS total_rows,
               SUM(CASE WHEN turnover_rate IS NULL THEN 1 ELSE 0 END) AS null_turnover,
               SUM(CASE WHEN volume_ratio IS NULL THEN 1 ELSE 0 END) AS null_volume_ratio,
               SUM(CASE WHEN total_share IS NULL THEN 1 ELSE 0 END) AS null_total_share,
               MIN(trade_date) AS min_date,
               MAX(trade_date) AS max_date
        FROM mart_daily_quotes
        WHERE symbol = ANY(%s)
        GROUP BY symbol;
        """,
        (list(symbols),),
    )
    rows = cur.fetchall()
    result = []
    for row in rows:
        entry = {
            "symbol": row[0],
            "total_rows": row[1],
            "null_turnover": row[2],
            "null_volume_ratio": row[3],
            "null_total_share": row[4],
            "min_date": row[5],
            "max_date": row[6],
        }
        allowed_null_volume = min(1, entry["total_rows"])
        volume_warn = entry["null_volume_ratio"] > allowed_null_volume
        turnover_warn = entry["null_turnover"] > entry["total_rows"] * 0.2  # arbitrary threshold
        share_warn = entry["null_total_share"] == entry["total_rows"]

        if volume_warn or turnover_warn or share_warn:
            LOGGER.warning("Monitoring warning: %s", entry)
        else:
            LOGGER.info("Monitoring: %s", entry)
        result.append(entry)
    return result
