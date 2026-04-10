"""
Yahoo Finance news scraper via Yahoo's search JSON API.
No API key required.
"""
from datetime import datetime, timezone
from typing import Generator

import requests

_BASE = "https://query2.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sentiment-scanner/1.0)"}


def fetch_posts(tickers: list) -> Generator[dict, None, None]:
    """Yield post dicts for each news article from Yahoo Finance."""
    for ticker in tickers:
        try:
            resp = requests.get(
                _BASE,
                params={"q": ticker, "newsCount": 10, "quotesCount": 0},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            articles = resp.json().get("news", [])

            for article in articles:
                title = (article.get("title") or "").strip()
                if not title:
                    continue

                # providerPublishTime is a Unix timestamp (seconds)
                pub_ts = article.get("providerPublishTime")
                published_at = (
                    datetime.fromtimestamp(pub_ts, tz=timezone.utc).replace(tzinfo=None)
                    if pub_ts else None
                )

                yield {
                    "source": "yahoo",
                    "external_id": str(article.get("uuid", f"{ticker}_{title[:20]}")),
                    "text": f"${ticker} {title}"[:2000],
                    "url": article.get("link", ""),
                    "raw_score": 0,
                    "published_at": published_at,
                }

        except Exception as exc:
            print(f"[yahoo] Error fetching news for {ticker}: {exc}")
