from datetime import datetime, timedelta, timezone
from typing import TypedDict

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; job-scraper/0.1)"


class Vacancy(TypedDict):
    source: str
    source_id: str
    title: str
    company: str
    location: str
    salary: str | None
    description: str
    remote_flag: bool
    raw_payload: dict


def http_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)


def cutoff_datetime(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
