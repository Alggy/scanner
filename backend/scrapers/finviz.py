"""
Finviz per-ticker news scraper.
Fetches recent headlines from finviz.com/quote.ashx?t={ticker}.
No API key required.
"""
import hashlib
import time
import re
from datetime import datetime, date
from typing import Generator

import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sentiment-scanner/1.0)"}
_DELAY = 0.5  # seconds between requests to avoid rate limiting

# Finviz date formats: "Apr-08-24" (with date) or "07:30AM" (time only, same day)
_DATE_RE = re.compile(r"^[A-Z][a-z]{2}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(AM|PM)$")


def _make_id(ticker: str, headline: str) -> str:
    return hashlib.sha1(f"{ticker}::{headline}".encode()).hexdigest()[:16]


def _parse_finviz_datetime(date_str: str, time_str: str):
    """Combine a Finviz date string and time string into a datetime, or None."""
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%b-%d-%y %I:%M%p")
        return dt
    except (ValueError, TypeError):
        return None


def fetch_posts(tickers: list) -> Generator[dict, None, None]:
    """Yield post dicts for each headline found on Finviz quote pages."""
    for ticker in tickers:
        try:
            url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            news_table = soup.find("table", id="news-table")
            if not news_table:
                continue

            current_date = datetime.utcnow().strftime("%b-%d-%y")  # fallback = today

            for row in news_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                date_cell = cells[0].get_text(strip=True)
                link = row.find("a", class_="tab-link-news")
                if not link:
                    continue

                headline = link.get_text(strip=True)
                href = link.get("href", "")
                if not headline:
                    continue

                # Date cell may be "Apr-08-24 07:30AM" or just "07:30AM"
                parts = date_cell.split()
                if len(parts) == 2 and _DATE_RE.match(parts[0]):
                    current_date = parts[0]
                    time_part = parts[1]
                elif len(parts) == 1 and _TIME_RE.match(parts[0]):
                    time_part = parts[0]
                else:
                    time_part = None

                published_at = _parse_finviz_datetime(current_date, time_part) if time_part else None

                yield {
                    "source": "finviz",
                    "external_id": _make_id(ticker, headline),
                    "text": f"${ticker} {headline}",
                    "url": href,
                    "raw_score": 0,
                    "published_at": published_at,
                }

        except Exception as exc:
            print(f"[finviz] Error scraping {ticker}: {exc}")
        finally:
            time.sleep(_DELAY)
