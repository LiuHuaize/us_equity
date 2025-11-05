from __future__ import annotations

import argparse
import csv
import logging
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .db import get_cursor


LOGGER = logging.getLogger(__name__)


MIN_TRADING_DAY_RATIO = 0.55


@dataclass
class EtfPerformance:
    symbol: str
    name: str
    start_date: date
    end_date: date
    holding_days: int
    total_return: Decimal
    annualized_return: Decimal


PERIOD_QUERY = """
WITH latest AS (
    SELECT max(mdq.trade_date) AS latest_date
    FROM mart_daily_quotes mdq
    JOIN dim_symbol ds ON ds.symbol = mdq.symbol
    WHERE ds.asset_type = 'ETF'
      AND ds.is_active
),
thresholds AS (
    SELECT latest_date,
           (latest_date - make_interval(years => %(window_years)s))::date AS start_cut
    FROM latest
),
eligibility AS (
    SELECT latest_date,
           (latest_date - make_interval(years => %(min_years)s))::date AS min_required_date
    FROM latest
),
eligible_symbols AS (
    SELECT mdq.symbol
    FROM mart_daily_quotes mdq
    JOIN dim_symbol ds ON ds.symbol = mdq.symbol
    JOIN eligibility e ON true
    JOIN thresholds t ON true
    WHERE ds.asset_type = 'ETF'
      AND ds.is_active
      AND NOT EXISTS (
          SELECT 1
          FROM fact_corporate_actions fca
          WHERE fca.symbol = mdq.symbol
            AND fca.action_type = 'split'
            AND fca.value < 1
            AND fca.action_date >= t.start_cut - make_interval(days => %(fudge_days)s)
      )
    GROUP BY mdq.symbol
    HAVING min(mdq.trade_date) <= min(e.min_required_date) + make_interval(days => %(fudge_days)s)
),
start_prices AS (
    SELECT DISTINCT ON (mdq.symbol) mdq.symbol,
           mdq.trade_date AS start_date,
           mdq.adjusted_close AS start_price
    FROM mart_daily_quotes mdq
    JOIN dim_symbol ds ON ds.symbol = mdq.symbol
    JOIN eligible_symbols es ON es.symbol = mdq.symbol
    JOIN thresholds t ON true
    WHERE ds.asset_type = 'ETF'
      AND ds.is_active
      AND mdq.adjusted_close IS NOT NULL
      AND mdq.trade_date >= t.start_cut
    ORDER BY mdq.symbol, mdq.trade_date
),
end_prices AS (
    SELECT mdq.symbol,
           mdq.trade_date AS end_date,
           mdq.adjusted_close AS end_price
    FROM mart_daily_quotes mdq
    JOIN eligible_symbols es ON es.symbol = mdq.symbol
    JOIN latest l ON l.latest_date = mdq.trade_date
),
coverage AS (
    SELECT mdq.symbol,
           COUNT(*) FILTER (
               WHERE mdq.trade_date BETWEEN t.start_cut AND l.latest_date
                 AND mdq.adjusted_close IS NOT NULL
           ) AS trading_days
    FROM mart_daily_quotes mdq
    JOIN eligible_symbols es ON es.symbol = mdq.symbol
    JOIN thresholds t ON true
    JOIN latest l ON true
    GROUP BY mdq.symbol
),
calc AS (
    SELECT sp.symbol,
           sp.start_date,
           ep.end_date,
           sp.start_price,
           ep.end_price,
           ep.end_price / sp.start_price - 1 AS total_return,
           power((ep.end_price / sp.start_price)::numeric,
                 (365.25 / GREATEST(1, (ep.end_date - sp.start_date)))::numeric) - 1 AS annualized_return,
           ep.end_date - sp.start_date AS holding_days
    FROM start_prices sp
    JOIN end_prices ep ON ep.symbol = sp.symbol
    WHERE ep.end_price > 0
      AND sp.start_price > 0
)
SELECT c.symbol,
       ds.name,
       c.start_date,
       c.end_date,
       c.holding_days,
       c.total_return,
       c.annualized_return
FROM calc c
JOIN dim_symbol ds ON ds.symbol = c.symbol
JOIN thresholds t ON true
JOIN coverage cov ON cov.symbol = c.symbol
WHERE c.end_date = t.latest_date
  AND c.start_date <= t.start_cut + make_interval(days => %(fudge_days)s)
  AND c.holding_days >= %(min_coverage_days)s
  AND cov.trading_days >= %(min_trading_days)s
ORDER BY c.total_return DESC;
"""


def fetch_period_performance(
    window_years: int,
    fudge_days: int,
    min_years: int,
    min_coverage_ratio: float,
) -> List[EtfPerformance]:
    min_coverage_days = max(window_years * 365 - fudge_days, 1)
    calendar_days = window_years * 365
    min_trading_days = max(math.ceil(calendar_days * min_coverage_ratio), 1)
    params = {
        "window_years": window_years,
        "fudge_days": fudge_days,
        "min_years": min_years,
        "min_coverage_days": min_coverage_days,
        "min_trading_days": min_trading_days,
    }
    with get_cursor() as cur:
        cur.execute(PERIOD_QUERY, params)
        rows = cur.fetchall()

    performances: List[EtfPerformance] = []
    for row in rows:
        performances.append(
            EtfPerformance(
                symbol=row[0],
                name=row[1],
                start_date=row[2],
                end_date=row[3],
                holding_days=row[4],
                total_return=row[5],
                annualized_return=row[6],
            )
        )
    return performances


def format_percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')):,.2f}%"


def limit_items(items: List[EtfPerformance], limit: Optional[int]) -> List[EtfPerformance]:
    if limit is None:
        return items
    return items[:limit]


def print_rankings(title: str, items: List[EtfPerformance], limit: Optional[int]) -> None:
    print(title)
    print("=" * len(title))
    headers = f"{'排名':>4}  {'代码':<12}  {'名称':<40}  {'起始日':<10}  {'终止日':<10}  {'累计收益':>12}  {'年化收益':>12}"
    print(headers)
    print("-" * len(headers))

    limited = limit_items(items, limit)
    for idx, perf in enumerate(limited, start=1):
        name_display = perf.name[:40]
        print(
            f"{idx:>4}  {perf.symbol:<12}  {name_display:<40}  "
            f"{perf.start_date:%Y-%m-%d}  {perf.end_date:%Y-%m-%d}  "
            f"{format_percent(perf.total_return):>12}  {format_percent(perf.annualized_return):>12}"
        )
    print(f"共 {len(items)} 条记录")


def print_overlap(overlap: Iterable[Dict[str, EtfPerformance]], limit: Optional[int]) -> None:
    data = list(overlap)
    print("重叠ETF")
    print("======")
    headers = (
        f"{'排名':>4}  {'代码':<12}  {'名称':<40}  {'5年累计':>12}  {'5年年化':>12}  "
        f"{'10年累计':>12}  {'10年年化':>12}"
    )
    print(headers)
    print("-" * len(headers))

    limited = limit_items(data, limit)
    for idx, record in enumerate(limited, start=1):
        perf5 = record["5y"]
        perf10 = record["10y"]
        name_display = perf5.name[:40]
        print(
            f"{idx:>4}  {perf5.symbol:<12}  {name_display:<40}  "
            f"{format_percent(perf5.total_return):>12}  {format_percent(perf5.annualized_return):>12}  "
            f"{format_percent(perf10.total_return):>12}  {format_percent(perf10.annualized_return):>12}"
        )
    print(f"共 {len(data)} 条记录")


def build_overlap(
    perf_5y: List[EtfPerformance], perf_10y: List[EtfPerformance]
) -> List[Dict[str, EtfPerformance]]:
    lookup_10y: Dict[str, EtfPerformance] = {item.symbol: item for item in perf_10y}
    overlap: List[Dict[str, EtfPerformance]] = []
    for item in perf_5y:
        match = lookup_10y.get(item.symbol)
        if match is not None:
            overlap.append({"5y": item, "10y": match})
    return overlap


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETF收益排行榜")
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="旧版参数，等同于同时设置 --top-5y 与 --top-10y",
    )
    parser.add_argument(
        "--top-5y",
        type=int,
        default=None,
        help="5年榜单前N名，默认输出全部",
    )
    parser.add_argument(
        "--top-10y",
        type=int,
        default=None,
        help="10年榜单前N名，默认输出全部",
    )
    parser.add_argument(
        "--fudge-days",
        type=int,
        default=7,
        help="允许起始日相对于窗口起点的最大偏差天数",
    )
    parser.add_argument(
        "--csv-dir",
        type=str,
        default=None,
        help="若指定则输出CSV文件至该目录",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="日志级别，默认INFO",
    )
    return parser.parse_args()


def resolve_top_args(args: argparse.Namespace) -> Dict[str, Optional[int]]:
    top_5y = args.top_5y if args.top_5y is not None else args.top
    top_10y = args.top_10y if args.top_10y is not None else args.top
    return {"5y": top_5y, "10y": top_10y}


def write_rankings_csv(path: Path, items: List[EtfPerformance]) -> None:
    fieldnames = [
        "rank",
        "symbol",
        "name",
        "start_date",
        "end_date",
        "holding_days",
        "total_return",
        "annualized_return",
    ]
    with path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for idx, perf in enumerate(items, start=1):
            writer.writerow(
                {
                    "rank": idx,
                    "symbol": perf.symbol,
                    "name": perf.name,
                    "start_date": perf.start_date.isoformat(),
                    "end_date": perf.end_date.isoformat(),
                    "holding_days": perf.holding_days,
                    "total_return": f"{perf.total_return}",
                    "annualized_return": f"{perf.annualized_return}",
                }
            )


def write_overlap_csv(path: Path, records: List[Dict[str, EtfPerformance]]) -> None:
    fieldnames = [
        "rank",
        "symbol",
        "name",
        "start_date_5y",
        "end_date_5y",
        "holding_days_5y",
        "total_return_5y",
        "annualized_return_5y",
        "start_date_10y",
        "end_date_10y",
        "holding_days_10y",
        "total_return_10y",
        "annualized_return_10y",
    ]
    with path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for idx, record in enumerate(records, start=1):
            perf5 = record["5y"]
            perf10 = record["10y"]
            writer.writerow(
                {
                    "rank": idx,
                    "symbol": perf5.symbol,
                    "name": perf5.name,
                    "start_date_5y": perf5.start_date.isoformat(),
                    "end_date_5y": perf5.end_date.isoformat(),
                    "holding_days_5y": perf5.holding_days,
                    "total_return_5y": f"{perf5.total_return}",
                    "annualized_return_5y": f"{perf5.annualized_return}",
                    "start_date_10y": perf10.start_date.isoformat(),
                    "end_date_10y": perf10.end_date.isoformat(),
                    "holding_days_10y": perf10.holding_days,
                    "total_return_10y": f"{perf10.total_return}",
                    "annualized_return_10y": f"{perf10.annualized_return}",
                }
            )


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    LOGGER.info("开始生成ETF收益榜单，允许偏差天数：%s", args.fudge_days)

    perf_5y = fetch_period_performance(
        window_years=5,
        fudge_days=args.fudge_days,
        min_years=10,
        min_coverage_ratio=MIN_TRADING_DAY_RATIO,
    )
    LOGGER.info("5年窗口覆盖ETF数量：%s", len(perf_5y))

    perf_10y = fetch_period_performance(
        window_years=10,
        fudge_days=args.fudge_days,
        min_years=10,
        min_coverage_ratio=MIN_TRADING_DAY_RATIO,
    )
    LOGGER.info("10年窗口覆盖ETF数量：%s", len(perf_10y))

    top_counts = resolve_top_args(args)
    limited_5y = limit_items(perf_5y, top_counts["5y"])
    limited_10y = limit_items(perf_10y, top_counts["10y"])

    overlap = build_overlap(limited_5y, limited_10y)
    LOGGER.info("重叠ETF数量：%s", len(overlap))

    print_rankings("5年涨幅榜", perf_5y, top_counts["5y"])
    print()
    print_rankings("10年涨幅榜", perf_10y, top_counts["10y"])
    print()
    print_overlap(overlap, None)

    if args.csv_dir:
        output_dir = Path(args.csv_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        file_5y = output_dir / "etf_rankings_5y.csv"
        file_10y = output_dir / "etf_rankings_10y.csv"
        file_overlap = output_dir / "etf_rankings_overlap.csv"

        write_rankings_csv(file_5y, limited_5y)
        write_rankings_csv(file_10y, limited_10y)
        write_overlap_csv(file_overlap, overlap)

        LOGGER.info("CSV 已写入：%s, %s, %s", file_5y, file_10y, file_overlap)


if __name__ == "__main__":
    main()
