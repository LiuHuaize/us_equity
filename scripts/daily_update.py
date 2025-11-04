from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Sequence

from requests import HTTPError

from .api_client import EODHDClient
from .config import get_config
from .db import get_connection
from .etl_loaders import (
    log_null_metrics,
    refresh_mart_daily_quotes,
    upsert_dividends,
    upsert_eod_quotes,
    upsert_fundamentals,
    upsert_splits,
    upsert_symbol,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    stream=sys.stdout,
)
LOGGER = logging.getLogger("daily_update")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily EODHD update after market close.")
    parser.add_argument("--date", type=str, help="Trading date (YYYY-MM-DD). If omitted, uses latest available.")
    parser.add_argument("--refresh-fundamentals", action="store_true", help="Refresh fundamentals for processed symbols.")
    parser.add_argument("--lookback-days", type=int, default=90, help="Days of history to include when refreshing mart.")
    parser.add_argument("--limit-symbols", type=int, help="Limit number of symbols for testing.")
    parser.add_argument("--skip-dividends", action="store_true", help="Skip dividends/splits fetching (faster).")
    return parser.parse_args()


def normalize_symbol(code: str, exchange: str) -> str:
    return code if "." in code else f"{code}.{exchange}"


def fetch_bulk_quotes(client: EODHDClient, trading_date: str) -> Dict[str, List[dict]]:
    LOGGER.info("Fetching bulk EOD quotes for %s", trading_date)
    result = defaultdict(list)
    payload = {"date": trading_date} if trading_date else {}
    bulk_rows = client.get("/eod-bulk-last-day/US", payload)
    for row in bulk_rows:
        symbol = normalize_symbol(row["code"], row.get("exchange_short_name", "US"))
        result[symbol].append(
            {
                "date": row["date"],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "adjusted_close": row.get("adjusted_close"),
                "volume": row.get("volume"),
            }
        )
    return result


def ensure_fundamentals(client: EODHDClient, symbols: Sequence[str]) -> Dict[str, dict]:
    fundamentals_map = {}
    for symbol in symbols:
        fundamentals = client.get(f"/fundamentals/{symbol}", {})
        fundamentals_map[symbol] = fundamentals
    return fundamentals_map


def process_daily_update(args: argparse.Namespace) -> None:
    cfg = get_config()
    client = EODHDClient(cfg.eodhd_token)

    trading_date = args.date
    if trading_date:
        datetime.strptime(trading_date, "%Y-%m-%d")

    quote_map = fetch_bulk_quotes(client, trading_date)
    symbols = list(quote_map.keys())
    if args.limit_symbols:
        symbols = symbols[: args.limit_symbols]

    LOGGER.info("Symbols fetched: %d", len(symbols))
    if not symbols:
        LOGGER.warning("No symbols returned from bulk endpoint.")
        return

    fundamentals_map: Dict[str, dict] = {}
    if args.refresh_fundamentals:
        fundamentals_map = ensure_fundamentals(client, symbols)

    start_date = (
        datetime.fromisoformat(quote_map[symbols[0]][0]["date"]) - timedelta(days=args.lookback_days)
    ).date()
    end_date = quote_map[symbols[0]][0]["date"]

    with get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT symbol FROM dim_symbol WHERE symbol = ANY(%s)", (symbols,))
            existing = {row[0] for row in cur.fetchall()}

            processed_symbols: List[str] = []

            for symbol in symbols:
                rows = quote_map[symbol]
                api_symbol = symbol
                fundamentals = fundamentals_map.get(symbol)
                if fundamentals:
                    general = fundamentals.get("General", {})
                    stored_symbol = general.get("PrimaryTicker") or general.get("Code") or symbol
                    stored_symbol = upsert_symbol(cur, stored_symbol, fundamentals)
                    upsert_fundamentals(cur, stored_symbol, fundamentals)
                    db_symbol = stored_symbol
                else:
                    db_symbol = symbol
                    if db_symbol not in existing:
                        fundamentals = client.get(f"/fundamentals/{api_symbol}", {})
                        fundamentals_map[symbol] = fundamentals
                        general = fundamentals.get("General", {})
                        stored_symbol = general.get("PrimaryTicker") or general.get("Code") or symbol
                        stored_symbol = upsert_symbol(cur, stored_symbol, fundamentals)
                        upsert_fundamentals(cur, stored_symbol, fundamentals)
                        db_symbol = stored_symbol
                        existing.add(db_symbol)

                upsert_eod_quotes(cur, db_symbol, rows)
                if db_symbol not in processed_symbols:
                    processed_symbols.append(db_symbol)

                if not args.skip_dividends:
                    dividends = client.get(f"/div/{api_symbol}", {"from": end_date, "to": end_date})
                    splits = client.get(f"/splits/{api_symbol}", {"from": end_date, "to": end_date})
                    upsert_dividends(cur, db_symbol, dividends)
                    upsert_splits(cur, db_symbol, splits)

            refresh_mart_daily_quotes(cur, processed_symbols, start_date.isoformat(), end_date)
            metrics = log_null_metrics(cur, processed_symbols)
            conn.commit()
            LOGGER.info("Daily update completed metrics=%s", metrics)
        except Exception:
            conn.rollback()
            LOGGER.exception("Daily update failed")
            raise
        finally:
            cur.close()


def main() -> None:
    args = parse_args()
    try:
        process_daily_update(args)
    except HTTPError as http_err:
        LOGGER.error("HTTP error: %s", http_err)
    except Exception as exc:
        LOGGER.error("Unexpected error: %s", exc)


if __name__ == "__main__":
    main()
