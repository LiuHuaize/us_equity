#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

PYTHON_PATH="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON_PATH" ]; then
  echo "Python venv not found at ${PYTHON_PATH}" >&2
  exit 1
fi

TARGET_DATE="${1:-}"
if [ -z "$TARGET_DATE" ]; then
  eastern_stamp="$(TZ="America/New_York" date +%F:%u)"
  date_part="${eastern_stamp%:*}"
  weekday="${eastern_stamp#*:}"
  if [ "$weekday" -eq 6 ]; then
    date_part="$(TZ="America/New_York" date -d "yesterday" +%F)"
  elif [ "$weekday" -eq 7 ]; then
    date_part="$(TZ="America/New_York" date -d "2 days ago" +%F)"
  fi
  TARGET_DATE="$date_part"
fi

LOOKBACK_DAYS="${LOOKBACK_DAYS:-120}"
REFRESH_FUNDAMENTALS="${REFRESH_FUNDAMENTALS:-true}"
SKIP_DIVIDENDS="${SKIP_DIVIDENDS:-false}"
ASSET_TYPES="${ASSET_TYPES:-}"
ONLY_KNOWN_SYMBOLS="${ONLY_KNOWN_SYMBOLS:-false}"
RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-3}"
RETRY_DELAY_SECONDS="${RETRY_DELAY_SECONDS:-300}"

cmd=("$PYTHON_PATH" -m scripts.daily_update --date "$TARGET_DATE" --lookback-days "$LOOKBACK_DAYS")
if [ "$REFRESH_FUNDAMENTALS" = "true" ]; then
  cmd+=(--refresh-fundamentals)
fi
if [ "$SKIP_DIVIDENDS" = "true" ]; then
  cmd+=(--skip-dividends)
fi
if [ -n "${LIMIT_SYMBOLS:-}" ]; then
  cmd+=(--limit-symbols "$LIMIT_SYMBOLS")
fi
if [ -n "$ASSET_TYPES" ]; then
  cmd+=(--asset-types "$ASSET_TYPES")
fi
if [ "$ONLY_KNOWN_SYMBOLS" = "true" ]; then
  cmd+=(--only-known-symbols)
fi

echo "[$(date -u +%F\ %T)] running daily_update for ${TARGET_DATE}"
attempt=1
while true; do
  if "${cmd[@]}"; then
    break
  fi
  if [ "$attempt" -ge "$RETRY_ATTEMPTS" ]; then
    echo "[$(date -u +%F\ %T)] daily_update failed after ${attempt} attempts" >&2
    exit 1
  fi
  echo "[$(date -u +%F\ %T)] daily_update attempt ${attempt} failed, retrying in ${RETRY_DELAY_SECONDS}s" >&2
  sleep "$RETRY_DELAY_SECONDS"
  attempt=$((attempt + 1))
done
