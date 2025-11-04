from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_random_exponential

from .config import get_config


LOGGER = logging.getLogger(__name__)


class EODHDClient:
    BASE_URL = "https://eodhd.com/api"

    def __init__(self, token: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        cfg = get_config()
        self.token = token or cfg.eodhd_token
        self.timeout = cfg.request_timeout
        self.session = session or requests.Session()

    @retry(stop=stop_after_attempt(5), wait=wait_random_exponential(multiplier=1, max=8))
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.BASE_URL}{path}"
        payload = dict(params or {})
        payload["api_token"] = self.token
        payload.setdefault("fmt", "json")
        LOGGER.debug("GET %s params=%s", url, payload)
        response = self.session.get(url, params=payload, timeout=self.timeout)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "1"))
            LOGGER.warning("Rate limited by EODHD, sleeping for %s seconds", retry_after)
            time.sleep(retry_after)
            response = self.session.get(url, params=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
