from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

from .config import Settings, settings


class Database:
    def __init__(self, config: Settings) -> None:
        self._config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            host=self._config.pg_host,
            port=self._config.pg_port,
            user=self._config.pg_user,
            password=self._config.pg_password,
            database=self._config.pg_database,
            min_size=self._config.pg_pool_min_size,
            max_size=self._config.pg_pool_max_size,
        )

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool is not initialized; call connect() first.")
        return self._pool

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self.pool
        async with pool.acquire() as connection:
            yield connection


db = Database(settings)
