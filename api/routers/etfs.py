from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import settings
from ..deps import get_db_connection, verify_api_token
from ..schemas import (
    PerformancePoint,
    PerformanceSeries,
    PeriodicReturn,
    ReturnSeries,
    ReturnStats,
)


BUCKET_EXPRESSIONS = {
    "day": "f.trade_date",
    "month": "date_trunc('month', f.trade_date)::date",
    "year": "date_trunc('year', f.trade_date)::date",
}


router = APIRouter(
    prefix="/etfs",
    tags=["etfs"],
    dependencies=[Depends(verify_api_token)],
)


def _to_float(value: Optional[Decimal]) -> Optional[float]:
    return float(value) if value is not None else None


def _sort_records(records: Iterable[asyncpg.Record]) -> list[asyncpg.Record]:
    return sorted(records, key=lambda row: row["period_start"])


@router.get("/{symbol}/returns", response_model=ReturnSeries, summary="ETF 周期收益")
async def get_periodic_returns(
    symbol: str,
    period: str = Query("year", description="统计周期：'month' 或 'year'"),
    limit: int = Query(10, ge=1, le=240, description="返回的周期数量"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ReturnSeries:
    period_type = period.lower()
    if period_type not in {"month", "year"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period 必须是 month 或 year")

    rows = await conn.fetch(
        """
        SELECT period_key,
               period_start,
               period_end,
               trading_days,
               total_return_pct,
               compound_return_pct,
               volatility_pct,
               max_drawdown_pct
        FROM mart_etf_periodic_returns
        WHERE symbol = $1
          AND period_type = $2
        ORDER BY period_start DESC
        LIMIT $3
        """,
        symbol,
        period_type,
        limit,
    )

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该标的的收益数据")

    payload = [
        PeriodicReturn(
            period_key=row["period_key"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            trading_days=row["trading_days"],
            total_return_pct=_to_float(row["total_return_pct"]),
            compound_return_pct=_to_float(row["compound_return_pct"]),
            volatility_pct=_to_float(row["volatility_pct"]),
            max_drawdown_pct=_to_float(row["max_drawdown_pct"]),
        )
        for row in rows
    ]

    return ReturnSeries(symbol=symbol, period=period_type, rows=payload)


@router.get(
    "/{symbol}/performance",
    response_model=PerformanceSeries,
    summary="ETF 与基准的累计收益对比",
)
async def get_performance_series(
    symbol: str,
    interval: str = Query(
        "day",
        description="聚合粒度：'day'、'month' 或 'year'",
    ),
    years: int = Query(
        settings.default_return_years,
        ge=1,
        le=30,
        description="向后统计的年份跨度",
    ),
    benchmark: Optional[str] = Query(
        None,
        description="对比基准的 symbol，默认为 ETF_DEFAULT_BENCHMARK",
    ),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> PerformanceSeries:
    interval_key = interval.lower()
    if interval_key not in BUCKET_EXPRESSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="interval 必须是 day、month 或 year")

    benchmark_symbol = benchmark or settings.default_benchmark_symbol
    if benchmark_symbol == symbol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="基准 symbol 不可与标的一致")

    bucket_expr = BUCKET_EXPRESSIONS[interval_key]
    query = f"""
        WITH symbol_bounds AS (
            SELECT symbol,
                   MIN(trade_date) AS min_date,
                   MAX(trade_date) AS max_date
            FROM mart_daily_quotes
            WHERE symbol = ANY($1)
              AND adjusted_close IS NOT NULL
              AND adjusted_close > 0
            GROUP BY symbol
        ),
        available AS (
            SELECT
                MIN(max_date) AS end_date,
                MAX(min_date) AS min_shared_date,
                COUNT(*) AS symbol_count
            FROM symbol_bounds
        ),
        range_bounds AS (
            SELECT
                end_date,
                GREATEST(
                    (end_date - make_interval(years => $2))::date,
                    min_shared_date
                ) AS start_date
            FROM available
            WHERE end_date IS NOT NULL
              AND min_shared_date IS NOT NULL
              AND symbol_count >= 2
        ),
        filtered AS (
            SELECT mdq.symbol,
                   mdq.trade_date,
                   mdq.adjusted_close
            FROM mart_daily_quotes mdq
            JOIN range_bounds rb
              ON mdq.trade_date BETWEEN rb.start_date AND rb.end_date
            WHERE mdq.symbol = ANY($1)
              AND mdq.adjusted_close IS NOT NULL
              AND mdq.adjusted_close > 0
        ),
        bucketed AS (
            SELECT
                f.symbol,
                {bucket_expr} AS bucket_date,
                f.trade_date,
                f.adjusted_close,
                ROW_NUMBER() OVER (PARTITION BY f.symbol, {bucket_expr} ORDER BY f.trade_date DESC) AS rn_desc
            FROM filtered f
        ),
        aggregated AS (
            SELECT
                symbol,
                bucket_date,
                adjusted_close
            FROM bucketed
            WHERE rn_desc = 1
        ),
        aligned AS (
            SELECT
                bucket_date,
                MAX(CASE WHEN symbol = $3 THEN adjusted_close END) AS etf_close,
                MAX(CASE WHEN symbol = $4 THEN adjusted_close END) AS benchmark_close
            FROM aggregated
            GROUP BY bucket_date
            HAVING COUNT(*) FILTER (WHERE symbol = $3) > 0
               AND COUNT(*) FILTER (WHERE symbol = $4) > 0
        )
        SELECT
            bucket_date,
            etf_close,
            benchmark_close
        FROM aligned
        ORDER BY bucket_date;
    """

    symbols = [symbol, benchmark_symbol]
    rows = await conn.fetch(query, symbols, years, symbol, benchmark_symbol)

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可用的价格数据")

    base_etf = float(rows[0]["etf_close"])
    base_benchmark = float(rows[0]["benchmark_close"])
    if base_etf <= 0 or base_benchmark <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="初始价格必须大于 0")

    points: list[PerformancePoint] = []
    for record in rows:
        etf_close = float(record["etf_close"])
        benchmark_close = float(record["benchmark_close"])
        if etf_close <= 0 or benchmark_close <= 0:
            continue

        etf_value = etf_close / base_etf
        benchmark_value = benchmark_close / base_benchmark
        etf_return = etf_value - 1.0
        benchmark_return = benchmark_value - 1.0

        points.append(
            PerformancePoint(
                date=record["bucket_date"],
                etf_value=etf_value,
                benchmark_value=benchmark_value,
                etf_cumulative_return_pct=etf_return,
                benchmark_cumulative_return_pct=benchmark_return,
                spread_pct=etf_return - benchmark_return,
            )
        )

    if not points:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="无法计算累计收益")

    start_date = points[0].date
    end_date = points[-1].date

    return PerformanceSeries(
        symbol=symbol,
        benchmark=benchmark_symbol,
        interval=interval_key,
        start_date=start_date,
        end_date=end_date,
        points=points,
    )


@router.get("/{symbol}/stats", response_model=ReturnStats, summary="ETF 周期收益统计")
async def get_return_stats(
    symbol: str,
    window_years: int = Query(
        settings.default_return_years,
        ge=1,
        le=30,
        description="向后检索的年度周期数量",
    ),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ReturnStats:
    rows = await conn.fetch(
        """
        WITH bounds AS (
            SELECT
                MIN(mdq.trade_date) AS min_trade_date,
                MAX(mdq.trade_date) AS max_trade_date
            FROM mart_daily_quotes mdq
            WHERE mdq.symbol = $1
        ),
        range_bounds AS (
            SELECT
                max_trade_date,
                GREATEST(
                    min_trade_date,
                    (max_trade_date - make_interval(years => $2))::date
                ) AS start_cut
            FROM bounds
        ),
        actual_bounds AS (
            SELECT
                (SELECT MIN(trade_date)
                 FROM mart_daily_quotes
                 WHERE symbol = $1
                   AND trade_date >= rb.start_cut) AS window_start,
                rb.max_trade_date AS window_end
            FROM range_bounds rb
        ),
        price_bounds AS (
            SELECT
                ab.window_start,
                ab.window_end,
                (SELECT adjusted_close
                 FROM mart_daily_quotes
                 WHERE symbol = $1
                   AND trade_date = ab.window_start) AS start_price,
                (SELECT adjusted_close
                 FROM mart_daily_quotes
                 WHERE symbol = $1
                   AND trade_date = ab.window_end) AS end_price
            FROM actual_bounds ab
        )
        SELECT
            r.period_key,
            r.period_start,
            r.period_end,
            r.total_return_pct,
            r.compound_return_pct,
            r.volatility_pct,
            r.max_drawdown_pct,
            ab.window_start,
            ab.window_end,
            pb.start_price,
            pb.end_price
        FROM mart_etf_periodic_returns r
        CROSS JOIN actual_bounds ab
        CROSS JOIN price_bounds pb
        WHERE r.symbol = $1
          AND r.period_type = 'year'
          AND ab.window_start IS NOT NULL
          AND r.period_end >= ab.window_start
          AND r.period_start <= ab.window_end
        ORDER BY r.period_start DESC
        """,
        symbol,
        window_years,
    )

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到年度收益数据")

    window_start = rows[0]["window_start"] if rows and rows[0]["window_start"] is not None else None
    window_end = rows[0]["window_end"] if rows and rows[0]["window_end"] is not None else None
    start_price = rows[0]["start_price"] if rows else None
    end_price = rows[0]["end_price"] if rows else None

    ordered_rows = _sort_records(rows)
    total_periods = len(ordered_rows)

    product = 1.0
    valid_returns = 0
    for record in ordered_rows:
        period_return = record["compound_return_pct"] or record["total_return_pct"]
        if period_return is None:
            continue
        product *= 1.0 + float(period_return)
        valid_returns += 1

    total_return: Optional[float] = None
    if start_price and end_price and start_price > 0:
        total_return = float(end_price / start_price) - 1.0
    elif valid_returns:
        total_return = product - 1.0

    average_annual: Optional[float] = None
    if total_return is not None and window_start and window_end and window_end > window_start:
        span_days = (window_end - window_start).days
        if span_days > 0:
            average_annual = (1.0 + total_return) ** (365.25 / span_days) - 1.0

    if average_annual is None and valid_returns:
        average_annual = product ** (1.0 / valid_returns) - 1.0

    max_drawdown: Optional[float] = None
    for record in ordered_rows:
        drawdown = _to_float(record["max_drawdown_pct"])
        if drawdown is None:
            continue
        max_drawdown = drawdown if max_drawdown is None or drawdown < max_drawdown else max_drawdown

    volatility_samples = [float(record["volatility_pct"]) for record in ordered_rows if record["volatility_pct"] is not None]
    average_volatility = (sum(volatility_samples) / len(volatility_samples)) if volatility_samples else None

    best_record = max(
        (record for record in ordered_rows if record["total_return_pct"] is not None),
        key=lambda item: item["total_return_pct"],
        default=None,
    )
    worst_record = min(
        (record for record in ordered_rows if record["total_return_pct"] is not None),
        key=lambda item: item["total_return_pct"],
        default=None,
    )

    return ReturnStats(
        symbol=symbol,
        window_years=window_years,
        periods=total_periods,
        total_return_pct=total_return,
        average_annual_return_pct=average_annual,
        max_drawdown_pct=max_drawdown,
        average_volatility_pct=average_volatility,
        best_period_key=best_record["period_key"] if best_record else None,
        best_period_return_pct=_to_float(best_record["total_return_pct"]) if best_record else None,
        worst_period_key=worst_record["period_key"] if worst_record else None,
        worst_period_return_pct=_to_float(worst_record["total_return_pct"]) if worst_record else None,
        start_date=window_start or ordered_rows[0]["period_start"],
        end_date=window_end or ordered_rows[-1]["period_end"],
    )
