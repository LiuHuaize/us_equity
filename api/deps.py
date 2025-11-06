from __future__ import annotations

from typing import AsyncIterator, Optional

import asyncpg
from fastapi import Header, HTTPException, status

from .config import settings
from .db import db


async def get_db_connection() -> AsyncIterator[asyncpg.Connection]:
    async with db.acquire() as connection:
        yield connection


async def verify_api_token(x_api_token: Optional[str] = Header(default=None)) -> None:
    if settings.api_auth_token and x_api_token != settings.api_auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
