import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass
class AppConfig:
    eodhd_token: str
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "us_equity"
    pg_user: str = "eodhd_app"
    pg_password: Optional[str] = None
    request_timeout: int = 30


def get_config() -> AppConfig:
    token = os.getenv("EODHD_API_TOKEN")
    if not token:
        raise RuntimeError("EODHD_API_TOKEN is not set in environment.")

    password = os.getenv("PGPASSWORD")

    return AppConfig(
        eodhd_token=token,
        pg_host=os.getenv("PGHOST", "localhost"),
        pg_port=int(os.getenv("PGPORT", "5432")),
        pg_database=os.getenv("PGDATABASE", "us_equity"),
        pg_user=os.getenv("PGUSER", "eodhd_app"),
        pg_password=password,
        request_timeout=int(os.getenv("EODHD_TIMEOUT", "30")),
    )

