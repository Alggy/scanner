"""
Market hours helpers.
Uses zoneinfo (Python 3.9 stdlib) — no pytz needed.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    """Current datetime in US/Eastern."""
    return datetime.now(_ET)


def use_premarket_sort() -> bool:
    """
    Return True if the current ET time is before 10:00 AM.
    Before 10 AM we sort the watchlist by Yahoo Finance pre-market %.
    At/after 10 AM we switch to live Finviz intraday %.
    """
    t = now_et()
    return t.hour < 10


def get_session() -> str:
    """
    Returns one of:
      'premarket'   — before 9:30 AM ET
      'open'        — 9:30 AM–4:00 PM ET
      'after_hours' — after 4:00 PM ET
    """
    t = now_et()
    minutes = t.hour * 60 + t.minute
    if minutes < 9 * 60 + 30:
        return "premarket"
    if minutes < 16 * 60:
        return "open"
    return "after_hours"
