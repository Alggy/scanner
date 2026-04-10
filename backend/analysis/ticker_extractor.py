from __future__ import annotations

import re
import os
import csv
from functools import lru_cache
from typing import Generator

CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Common English words that look like tickers — filter them out
WORD_BLOCKLIST = {
    "A", "I", "IT", "BE", "DO", "GO", "AT", "IN", "ON", "OR", "IF",
    "FOR", "THE", "AND", "BUT", "NOW", "ALL", "ARE", "NEW", "BIG",
    "CAN", "GET", "GOT", "HAS", "HAD", "HIM", "HIS", "HOW", "ITS",
    "LET", "MAY", "NOT", "OFF", "OLD", "OUR", "OUT", "OWN", "PUT",
    "SAY", "SEE", "SET", "SHE", "SO", "TOO", "TWO", "USE", "WAS",
    "WAY", "WE", "WHO", "WHY", "YET", "YOU",
    # Common financial non-tickers
    "USD", "ETF", "CEO", "CFO", "IPO", "ATH", "ATL", "DD", "WSB",
    "YOLO", "FUD", "FOMO", "BUY", "SELL", "LONG", "SHORT",
}


@lru_cache(maxsize=1)
def _load_valid_tickers() -> frozenset[str]:
    ticker_file = os.path.join(os.path.dirname(__file__), "tickers.csv")
    if not os.path.exists(ticker_file):
        return frozenset()
    tickers = set()
    with open(ticker_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("Symbol") or row.get("symbol") or row.get("Ticker") or ""
            tickers.add(symbol.strip().upper())
    return frozenset(tickers)


def extract_tickers(text: str) -> list[str]:
    """Return deduplicated list of valid tickers found in text."""
    raw = set(CASHTAG_RE.findall(text.upper()))
    valid = _load_valid_tickers()

    results = []
    for t in raw:
        if t in WORD_BLOCKLIST:
            continue
        # If ticker list loaded, only keep known tickers; otherwise keep all
        if valid and t not in valid:
            continue
        results.append(t)
    return results


def extract_ticker_post_pairs(posts: list[dict]) -> Generator[tuple[str, dict], None, None]:
    """Yield (ticker, post) for every ticker found in each post."""
    for post in posts:
        tickers = extract_tickers(post["text"])
        for ticker in tickers:
            yield ticker, post
