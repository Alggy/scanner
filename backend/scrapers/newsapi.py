"""
NewsAPI scraper — https://newsapi.org
Free tier: 100 requests/day. Requires NEWSAPI_KEY env var.
Optional: scanner runs fine without it.
"""
import hashlib
import os
from datetime import datetime
from typing import Generator

import requests

_BASE = "https://newsapi.org/v2/everything"
_PAGE_SIZE = 10


def _make_id(ticker: str, url: str) -> str:
    return hashlib.sha1(f"{ticker}::{url}".encode()).hexdigest()[:16]


def fetch_posts(tickers: list) -> Generator[dict, None, None]:
    """Yield post dicts for each news article returned by NewsAPI."""
    api_key = os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        return  # silently skip if key not configured

    for ticker in tickers:
        try:
            resp = requests.get(
                _BASE,
                params={
                    "q": f"{ticker} stock",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": _PAGE_SIZE,
                    "apiKey": api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            for article in data.get("articles", []):
                title = (article.get("title") or "").strip()
                description = (article.get("description") or "").strip()
                url = article.get("url", "")
                if not title or title == "[Removed]":
                    continue

                # publishedAt is ISO 8601: "2024-04-08T07:30:00Z"
                pub_str = article.get("publishedAt", "")
                try:
                    published_at = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ")
                except (ValueError, TypeError):
                    published_at = None

                text = f"${ticker} {title}"
                if description:
                    text = f"{text} — {description}"
                text = text[:2000]

                yield {
                    "source": "newsapi",
                    "external_id": _make_id(ticker, url),
                    "text": text,
                    "url": url,
                    "raw_score": 0,
                    "published_at": published_at,
                }

        except Exception as exc:
            print(f"[newsapi] Error fetching {ticker}: {exc}")
