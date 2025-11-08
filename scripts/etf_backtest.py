from __future__ import annotations

import argparse
import csv
import logging
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import pstdev
from typing import Dict, List, Optional, Sequence, Tuple

from .db import get_cursor


DEFAULT_START_DATE = date(2020, 11, 3)
DEFAULT_END_DATE = date(2025, 11, 3)


@dataclass(frozen=True)
class PortfolioDefinition:
    key: str
    label: str
    symbols: Sequence[str]


PORTFOLIOS: Dict[str, PortfolioDefinition] = {
    "top10_10y": PortfolioDefinition(
        key="top10_10y",
        label="10年榜前10",
        symbols=(
            "GBTC.US",
            "USD.US",
            "TECL.US",
            "SOXL.US",
            "TQQQ.US",
            "ROM.US",
            "QLD.US",
            "SMH.US",
            "SOXX.US",
            "SPXL.US",
        ),
    ),
    "top10_5y": PortfolioDefinition(
        key="top10_5y",
        label="5年榜前10",
        symbols=(
            "USD.US",
            "ERX.US",
            "DIG.US",
            "GBTC.US",
            "TECL.US",
            "URA.US",
            "GUSH.US",
            "SPXL.US",
            "FAS.US",
            "UPRO.US",
        ),
    ),
}


@dataclass
class PortfolioSeries:
    nav_points: List[Tuple[date, Decimal]]
    daily_returns: List[Optional[Decimal]]
    drawdowns: List[Decimal]
    max_drawdown: Decimal
    max_drawdown_start: date
    max_drawdown_end: date


@dataclass
class PortfolioSummary:
    key: str
    label: str
    start_date: date
    end_date: date
    trading_days: int
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    max_drawdown_start: date
    max_drawdown_end: date
    sharpe_ratio: Optional[float]
    calmar_ratio: Optional[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETF榜单组合回测工具")
    parser.add_argument(
        "--start-date",
        type=str,
        default=DEFAULT_START_DATE.isoformat(),
        help="回测起始日，默认2020-11-03",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=DEFAULT_END_DATE.isoformat(),
        help="回测截止日，默认2025-11-03",
    )
    parser.add_argument(
        "--portfolios",
        nargs="+",
        choices=list(PORTFOLIOS.keys()),
        default=list(PORTFOLIOS.keys()),
        help="需要回测的组合，默认全部",
    )
    parser.add_argument(
        "--summary-csv",
        type=str,
        default=None,
        help="若指定则输出汇总结果CSV",
    )
    parser.add_argument(
        "--nav-csv",
        type=str,
        default=None,
        help="若指定则输出组合净值明细CSV",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.0,
        help="年化无风险收益率，用于Sharpe/Calmar计算，默认0",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="日志级别，默认INFO",
    )
    return parser.parse_args()


def parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse已保证合法
        raise argparse.ArgumentTypeError(f"{label}必须是YYYY-MM-DD格式: {value}") from exc


def fetch_adjusted_prices(symbols: Sequence[str], start_date: date, end_date: date) -> Dict[str, Dict[date, Decimal]]:
    query = """
        SELECT symbol, trade_date, adjusted_close
        FROM mart_daily_quotes
        WHERE symbol = ANY(%s)
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date
    """
    price_map: Dict[str, Dict[date, Decimal]] = {sym: {} for sym in symbols}
    with get_cursor() as cur:
        cur.execute(query, (list(symbols), start_date, end_date))
        for symbol, trade_date, adj_close in cur.fetchall():
            if adj_close is None:
                continue
            price_map[symbol][trade_date] = Decimal(adj_close)
    missing = [sym for sym, rows in price_map.items() if not rows]
    if missing:
        raise RuntimeError(f"以下标的在区间内没有价格数据: {', '.join(missing)}")
    return price_map


def _first_available_date(rows: Dict[date, Decimal], start: date, end: date) -> date:
    candidates = [dt for dt in rows.keys() if start <= dt <= end]
    if not candidates:
        raise RuntimeError("所选区间内没有可用交易日")
    return min(candidates)


def build_portfolio_series(
    symbols: Sequence[str],
    price_map: Dict[str, Dict[date, Decimal]],
    start_date: date,
    end_date: date,
) -> PortfolioSeries:
    first_dates: Dict[str, date] = {}
    for sym in symbols:
        symbol_rows = price_map.get(sym)
        if not symbol_rows:
            raise RuntimeError(f"{sym} 在指定区间缺少价格数据")
        first_dates[sym] = _first_available_date(symbol_rows, start_date, end_date)

    effective_start = max(first_dates.values())
    if effective_start > start_date:
        logging.warning("部分标的缺少起始日收盘价，自动将起点平移到 %s", effective_start)

    relevant_dates = sorted(
        {
            dt
            for sym in symbols
            for dt in price_map[sym].keys()
            if effective_start <= dt <= end_date
        }
    )
    if not relevant_dates:
        raise RuntimeError("未获取到有效交易日，无法计算净值")

    weight = Decimal("1") / Decimal(len(symbols))
    last_prices: Dict[str, Optional[Decimal]] = {sym: None for sym in symbols}
    base_prices: Dict[str, Decimal] = {}
    nav_points: List[Tuple[date, Decimal]] = []

    for dt in relevant_dates:
        nav = Decimal("0")
        for sym in symbols:
            price = price_map[sym].get(dt)
            if price is not None:
                last_prices[sym] = price
            price = last_prices[sym]
            if price is None:
                raise RuntimeError(f"{sym} 在 {dt} 缺少可用于前复权的价格")
            if sym not in base_prices:
                base_prices[sym] = price
            nav += weight * (price / base_prices[sym])
        nav_points.append((dt, nav))

    daily_returns: List[Optional[Decimal]] = []
    drawdowns: List[Decimal] = []
    peak_nav = nav_points[0][1]
    peak_date = nav_points[0][0]
    max_drawdown = Decimal("0")
    max_drawdown_start = peak_date
    max_drawdown_end = peak_date
    prev_nav: Optional[Decimal] = None

    for dt, nav in nav_points:
        if prev_nav is None:
            daily_returns.append(None)
        else:
            daily_returns.append(nav / prev_nav - Decimal("1"))
        if nav > peak_nav:
            peak_nav = nav
            peak_date = dt
        drawdown = nav / peak_nav - Decimal("1")
        drawdowns.append(drawdown)
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_drawdown_start = peak_date
            max_drawdown_end = dt
        prev_nav = nav

    return PortfolioSeries(
        nav_points=nav_points,
        daily_returns=daily_returns,
        drawdowns=drawdowns,
        max_drawdown=max_drawdown,
        max_drawdown_start=max_drawdown_start,
        max_drawdown_end=max_drawdown_end,
    )


def compute_summary(
    definition: PortfolioDefinition,
    series: PortfolioSeries,
    risk_free_rate: float,
) -> PortfolioSummary:
    start_dt = series.nav_points[0][0]
    end_dt = series.nav_points[-1][0]
    trading_days = len(series.nav_points)
    nav_start = float(series.nav_points[0][1])
    nav_end = float(series.nav_points[-1][1])
    cumulative_return = nav_end - 1.0
    holding_days = max((end_dt - start_dt).days, 1)
    growth_ratio = nav_end / nav_start if nav_start else 0.0
    annualized_return = math.pow(growth_ratio, 365.25 / holding_days) - 1 if growth_ratio > 0 else 0.0
    daily_return_values = [float(ret) for ret in series.daily_returns if ret is not None]
    if len(daily_return_values) > 1:
        daily_vol = pstdev(daily_return_values)
    else:
        daily_vol = abs(daily_return_values[0]) if daily_return_values else 0.0
    annualized_volatility = daily_vol * math.sqrt(252)
    max_drawdown = float(series.max_drawdown)
    excess_return = annualized_return - risk_free_rate
    sharpe_ratio = excess_return / annualized_volatility if annualized_volatility > 0 else None
    calmar_ratio = excess_return / abs(max_drawdown) if max_drawdown < 0 else None

    return PortfolioSummary(
        key=definition.key,
        label=definition.label,
        start_date=start_dt,
        end_date=end_dt,
        trading_days=trading_days,
        cumulative_return=cumulative_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        max_drawdown=max_drawdown,
        max_drawdown_start=series.max_drawdown_start,
        max_drawdown_end=series.max_drawdown_end,
        sharpe_ratio=sharpe_ratio,
        calmar_ratio=calmar_ratio,
    )


def format_percent(value: float) -> str:
    return f"{value * 100:>8.2f}%"


def format_ratio(value: Optional[float]) -> str:
    if value is None or math.isnan(value):
        return "   N/A"
    return f"{value:>7.2f}"


def print_summary_table(summaries: Sequence[PortfolioSummary]) -> None:
    headers = (
        "组合",
        "起始日",
        "终止日",
        "交易日数",
        "累计收益",
        "年化收益",
        "年化波动",
        "最大回撤",
        "Sharpe",
        "Calmar",
    )
    print(" | ".join(headers))
    print("-" * 110)
    for summary in summaries:
        row = [
            summary.label,
            summary.start_date.isoformat(),
            summary.end_date.isoformat(),
            f"{summary.trading_days:>5}",
            format_percent(summary.cumulative_return),
            format_percent(summary.annualized_return),
            format_percent(summary.annualized_volatility),
            format_percent(summary.max_drawdown),
            format_ratio(summary.sharpe_ratio),
            format_ratio(summary.calmar_ratio),
        ]
        print(" | ".join(row))


def write_summary_csv(path: Path, summaries: Sequence[PortfolioSummary]) -> None:
    fieldnames = [
        "key",
        "label",
        "start_date",
        "end_date",
        "trading_days",
        "cumulative_return",
        "annualized_return",
        "annualized_volatility",
        "max_drawdown",
        "max_drawdown_start",
        "max_drawdown_end",
        "sharpe_ratio",
        "calmar_ratio",
    ]
    with path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "key": summary.key,
                    "label": summary.label,
                    "start_date": summary.start_date.isoformat(),
                    "end_date": summary.end_date.isoformat(),
                    "trading_days": summary.trading_days,
                    "cumulative_return": summary.cumulative_return,
                    "annualized_return": summary.annualized_return,
                    "annualized_volatility": summary.annualized_volatility,
                    "max_drawdown": summary.max_drawdown,
                    "max_drawdown_start": summary.max_drawdown_start.isoformat(),
                    "max_drawdown_end": summary.max_drawdown_end.isoformat(),
                    "sharpe_ratio": summary.sharpe_ratio if summary.sharpe_ratio is not None else "",
                    "calmar_ratio": summary.calmar_ratio if summary.calmar_ratio is not None else "",
                }
            )


def write_nav_csv(path: Path, portfolio_key: str, series: PortfolioSeries) -> None:
    fieldnames = ["portfolio", "trade_date", "nav", "daily_return", "drawdown"]
    mode = "w" if not path.exists() else "a"
    with path.open(mode, newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        for (dt, nav), daily_ret, drawdown in zip(series.nav_points, series.daily_returns, series.drawdowns):
            writer.writerow(
                {
                    "portfolio": portfolio_key,
                    "trade_date": dt.isoformat(),
                    "nav": float(nav),
                    "daily_return": float(daily_ret) if daily_ret is not None else "",
                    "drawdown": float(drawdown),
                }
            )


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    start_date = parse_date(args.start_date, "start_date")
    end_date = parse_date(args.end_date, "end_date")
    if end_date <= start_date:
        raise ValueError("结束日期必须晚于起始日期")
    selected_defs = [PORTFOLIOS[key] for key in args.portfolios]
    all_symbols: List[str] = sorted({sym for definition in selected_defs for sym in definition.symbols})
    price_map = fetch_adjusted_prices(all_symbols, start_date, end_date)

    summaries: List[PortfolioSummary] = []
    nav_outputs: Dict[str, PortfolioSeries] = {}

    for definition in selected_defs:
        logging.info("开始回测组合：%s", definition.label)
        series = build_portfolio_series(definition.symbols, price_map, start_date, end_date)
        nav_outputs[definition.key] = series
        summary = compute_summary(definition, series, args.risk_free_rate)
        summaries.append(summary)

    print_summary_table(summaries)

    if args.summary_csv:
        summary_path = Path(args.summary_csv)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        write_summary_csv(summary_path, summaries)
        logging.info("汇总结果已输出到 %s", summary_path)

    if args.nav_csv:
        nav_path = Path(args.nav_csv)
        nav_path.parent.mkdir(parents=True, exist_ok=True)
        if nav_path.exists():
            nav_path.unlink()
        for definition in selected_defs:
            write_nav_csv(nav_path, definition.key, nav_outputs[definition.key])
        logging.info("净值明细已输出到 %s", nav_path)


if __name__ == "__main__":
    main()
