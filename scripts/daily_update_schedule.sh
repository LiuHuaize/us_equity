#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${REPO_ROOT}/scripts/run_daily_update.sh"

if [ ! -x "$RUNNER" ]; then
  echo "Runner script not found at $RUNNER" >&2
  exit 1
fi

TARGET_DATE="${1:-}"

FAST_SKIP_DIVIDENDS="${FAST_SKIP_DIVIDENDS:-true}"
FAST_REFRESH_FUNDAMENTALS="${FAST_REFRESH_FUNDAMENTALS:-false}"
FAST_LOOKBACK_DAYS="${FAST_LOOKBACK_DAYS:-120}"
FAST_ASSET_TYPES="${FAST_ASSET_TYPES:-Common Stock,ETF}"
FAST_ONLY_KNOWN_SYMBOLS="${FAST_ONLY_KNOWN_SYMBOLS:-true}"
FAST_LIMIT_SYMBOLS="${FAST_LIMIT_SYMBOLS:-}"

FULL_SKIP_DIVIDENDS="${FULL_SKIP_DIVIDENDS:-false}"
FULL_REFRESH_FUNDAMENTALS="${FULL_REFRESH_FUNDAMENTALS:-true}"
FULL_LOOKBACK_DAYS="${FULL_LOOKBACK_DAYS:-120}"
FULL_ASSET_TYPES="${FULL_ASSET_TYPES:-Common Stock,ETF}"
FULL_ONLY_KNOWN_SYMBOLS="${FULL_ONLY_KNOWN_SYMBOLS:-true}"
FULL_LIMIT_SYMBOLS="${FULL_LIMIT_SYMBOLS:-}"

SECOND_RUN_DELAY_SECONDS="${SECOND_RUN_DELAY_SECONDS:-7200}"

run_phase() {
  local phase_name="$1"
  local skip_dividends="$2"
  local refresh_fundamentals="$3"
  local lookback_days="$4"
  local asset_types="$5"
  local only_known="$6"
  local limit_symbols="$7"

  local args=()
  if [ -n "$TARGET_DATE" ]; then
    args=("$TARGET_DATE")
  fi

  echo "[$(date -u +%F\ %T)] Starting ${phase_name} run (target=${TARGET_DATE:-auto})"
  env \
    SKIP_DIVIDENDS="$skip_dividends" \
    REFRESH_FUNDAMENTALS="$refresh_fundamentals" \
    LOOKBACK_DAYS="$lookback_days" \
    ASSET_TYPES="$asset_types" \
    ONLY_KNOWN_SYMBOLS="$only_known" \
    LIMIT_SYMBOLS="$limit_symbols" \
    "$RUNNER" "${args[@]}"
  echo "[$(date -u +%F\ %T)] Completed ${phase_name} run"
}

run_phase "fast" "$FAST_SKIP_DIVIDENDS" "$FAST_REFRESH_FUNDAMENTALS" "$FAST_LOOKBACK_DAYS" "$FAST_ASSET_TYPES" "$FAST_ONLY_KNOWN_SYMBOLS" "$FAST_LIMIT_SYMBOLS"

echo "[$(date -u +%F\ %T)] Sleeping ${SECOND_RUN_DELAY_SECONDS}s before full run"
sleep "$SECOND_RUN_DELAY_SECONDS"

run_phase "full" "$FULL_SKIP_DIVIDENDS" "$FULL_REFRESH_FUNDAMENTALS" "$FULL_LOOKBACK_DAYS" "$FULL_ASSET_TYPES" "$FULL_ONLY_KNOWN_SYMBOLS" "$FULL_LIMIT_SYMBOLS"
