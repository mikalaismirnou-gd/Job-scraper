import csv
import html
import re
import time
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_TAG_RE = re.compile(r"<[^>]+>")


def load_companies(filename: str) -> list[dict]:
    with open(CONFIG_DIR / filename, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    return _TAG_RE.sub(" ", unescaped).strip()


def polite_sleep(seconds: float = 0.3) -> None:
    time.sleep(seconds)
