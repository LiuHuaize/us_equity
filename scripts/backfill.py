from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from typing import List, Sequence

from requests import HTTPError

from .api_client import EODHDClient
from .config import get_config
from .db import get_connection
from .etl_loaders import (
    log_null_metrics,
    refresh_etf_periodic_returns,
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
LOGGER = logging.getLogger("backfill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical backfill for EODHD data.")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols (e.g., AAPL.US,MSFT.US)")
    parser.add_argument("--exchange", type=str, help="Exchange code for symbol list (NASDAQ, NYSE, AMEX).")
    parser.add_argument("--start", type=str, default="2014-01-01", help="Start date (YYYY-MM-DD).")
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.now(timezone.utc).date().isoformat(),
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between symbol processing.")
    parser.add_argument("--limit", type=int, help="Limit number of symbols processed.")
    return parser.parse_args()


def normalize_symbol(code: str, exchange: str) -> str:
    if "." in code:
        return code

    exchange_key = exchange.upper().strip()
    suffix_overrides = {
        "NASDAQ": "US",
        "NYSE": "US",
        "AMEX": "US",
        "US": "US",
        "NYSE ARCA": "US",
        "NYSEAMERICAN": "US",
        "NYSE AMERICAN": "US",
        "NYSE MKT": "US",
    }
    suffix = suffix_overrides.get(exchange_key, exchange_key.replace(" ", ""))
    return f"{code}.{suffix}"


def fetch_exchange_symbols(client: EODHDClient, exchange: str) -> List[str]:
    LOGGER.info("Fetching stock + ETF symbols for exchange %s", exchange)
    symbols: List[str] = []
    seen = set()
    for asset_kind in ("stock", "etf"):
        response = client.get(f"/exchange-symbol-list/{exchange}", {"type": asset_kind})
        for item in response:
            code = item.get("Code")
            if not code:
                continue
            normalized = normalize_symbol(code, item.get("Exchange", exchange))
            if normalized not in seen:
                symbols.append(normalized)
                seen.add(normalized)
    return symbols


def process_symbol(
    client: EODHDClient, symbol: str, start_date: str, end_date: str
) -> None:
    LOGGER.info("Processing %s", symbol)
    fundamentals = client.get(f"/fundamentals/{symbol}", {})
    general = fundamentals.get("General", {})
    stored_symbol = general.get("PrimaryTicker") or general.get("Code") or symbol

    eod_rows = client.get(f"/eod/{symbol}", {"from": start_date, "to": end_date})
    dividends = client.get(f"/div/{symbol}", {"from": start_date, "to": end_date})
    splits = client.get(f"/splits/{symbol}", {"from": "1900-01-01", "to": end_date})

    with get_connection() as conn:
        cur = conn.cursor()
        try:
            stored_symbol = upsert_symbol(cur, stored_symbol, fundamentals)
            upsert_fundamentals(cur, stored_symbol, fundamentals)
            upsert_eod_quotes(cur, stored_symbol, eod_rows)
            upsert_dividends(cur, stored_symbol, dividends)
            upsert_splits(cur, stored_symbol, splits)
            refresh_mart_daily_quotes(cur, [stored_symbol], start_date, end_date)
            refresh_etf_periodic_returns(cur, [stored_symbol], start_date, end_date)
            metrics = log_null_metrics(cur, [stored_symbol])
            conn.commit()
            LOGGER.info("Completed %s metrics=%s", stored_symbol, metrics)
        except Exception:
            conn.rollback()
            LOGGER.exception("Failed to process %s", stored_symbol)
            raise
        finally:
            cur.close()


def main() -> None:
    args = parse_args()
    cfg = get_config()
    client = EODHDClient(cfg.eodhd_token)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    elif args.exchange:
        symbols = fetch_exchange_symbols(client, args.exchange)
    else:
        raise SystemExit("Either --symbols or --exchange must be provided.")

    if args.limit:
        symbols = symbols[: args.limit]

    for idx, symbol in enumerate(symbols, start=1):
        try:
            process_symbol(client, symbol, args.start, args.end)
        except HTTPError as http_err:
            LOGGER.error("HTTP error for %s: %s", symbol, http_err)
        except Exception as exc:
            LOGGER.error("Unexpected error for %s: %s", symbol, exc)
        time.sleep(args.sleep)
        if idx % 50 == 0:
            LOGGER.info("Processed %d symbols", idx)


if __name__ == "__main__":
    main()
