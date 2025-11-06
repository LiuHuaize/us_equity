from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _get_env(name: str, default: Optional[str] = None, required: bool = True) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Environment variable {name} is required for API startup.")
    return value if value is not None else ""


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    pg_host: str = _get_env("PGHOST")
    pg_port: int = int(_get_env("PGPORT", "5432"))
    pg_database: str = _get_env("PGDATABASE")
    pg_user: str = _get_env("PGUSER")
    pg_password: str = _get_env("PGPASSWORD")
    pg_pool_min_size: int = int(os.getenv("PGPOOL_MIN_SIZE", "1"))
    pg_pool_max_size: int = int(os.getenv("PGPOOL_MAX_SIZE", "5"))
    api_auth_token: Optional[str] = os.getenv("API_AUTH_TOKEN")
    default_return_years: int = int(os.getenv("ETF_DEFAULT_RETURN_YEARS", "10"))
    default_benchmark_symbol: str = os.getenv("ETF_DEFAULT_BENCHMARK", "SPY.US")
    api_cors_origins: tuple[str, ...] = _split_csv(
        os.getenv("API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}@"
            f"{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


settings = Settings()
