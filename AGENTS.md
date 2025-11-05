# Repository Guidelines

## Project Structure & Module Organization
- `scripts/`: Python ETL modules (`api_client.py`, `backfill.py`, `daily_update.py`, `etl_loaders.py`). Treat them as CLI entry points by running `python -m scripts.<module>`.
- `docs/`: Operational runbooks and reference material. `docs/samples/` holds captured JSON payloads useful for offline parsing tests.
- `config/`: Reserved for deployment or orchestration assets; keep environment-specific secrets out of version control but document expected files here.

## Environment & Configuration
- Settings load from `.env` via `python-dotenv`; define `EODHD_API_TOKEN`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`.
- Activate a session with `export $(grep -v '^#' .env | xargs)` before running jobs, or explicitly set variables in your scheduler.
- Rotate API tokens regularly and avoid committing modified `.env` files or production credentials.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create an isolated environment.
- `pip install requests tenacity psycopg2-binary python-dotenv`: install runtime dependencies; add extras like `pytest` for local testing.
- `python -m scripts.backfill --symbols AAPL.US --start 2014-01-01`: run a historical load for selected symbols.
- `python -m scripts.daily_update --date 2024-01-05 --refresh-fundamentals`: execute the daily ingest and mart refresh for a specific trading date.

## Coding Style & Naming Conventions
- Use four-space indentation, type hints, and `snake_case` for functions and modules; classes stay in `CamelCase`.
- Initialize module-level loggers as `LOGGER = logging.getLogger(__name__)` and prefer structured log messages.
- Maintain financial precision with `Decimal` and reuse helpers from `utils.py` rather than redefining conversions.

## Testing Guidelines
- No automated suite exists yet; add `pytest` cases under `tests/` mirroring the `scripts/` layout.
- Favor deterministic tests that mock network access and reuse fixtures from `docs/samples/`.
- Run `pytest tests/test_utils.py -q` (or the relevant path) before submitting changes.

## Commit & Pull Request Guidelines
- History is currently sparse; follow an imperative one-line subject (≤72 chars) and include focused commits.
- Reference related issues, note required environment variables, and attach example command outputs in pull requests.
- Confirm that data-affecting scripts were run in a non-production database or clearly describe dry-run validation.

## Data Handling & Safety
- Treat database credentials and API responses as sensitive; redact payloads before sharing logs.
- When scripting ad-hoc analyses, write to temporary schemas or tables prefixed with your initials and clean them up afterward.

## 使用准则概览

- 回复语言必须使用简体中文。
- 开发过程中若有任何不确定之处，必须主动向用户提问。