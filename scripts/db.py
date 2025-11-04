from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg2

from .config import get_config


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    cfg = get_config()
    conn = psycopg2.connect(
        dbname=cfg.pg_database,
        user=cfg.pg_user,
        password=cfg.pg_password,
        host=cfg.pg_host,
        port=cfg.pg_port,
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(commit: bool = False) -> Generator[psycopg2.extensions.cursor, None, None]:
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

