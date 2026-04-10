"""
Dynamic watchlist built from Finviz top gainers + unusual volume screeners.

Globals (read by scheduler and API):
  CURRENT_TICKERS   — list[str] of ticker symbols used by scrapers
  CURRENT_WATCHLIST — list[dict] {rank, ticker, change_pct, price_source}, sorted descending
  CUSTOM_TICKERS    — list[str] of user-added tickers (set via PUT /api/watchlist/custom)
  LAST_REFRESHED    — ISO datetime string of last successful refresh (UTC)

Refresh schedule (see scheduler.py):
  • startup     — refresh_watchlist() called immediately
  • 08:00 AM ET — refresh_watchlist() (pre-market sort if before 10 AM)
  • 10:00 AM ET — refresh_watchlist() again so it switches to live Finviz %
"""
import datetime
import requests
from bs4 import BeautifulSoup

from backend.market_hours import use_premarket_sort
from backend.scrapers.prices import fetch_price_changes

# ── Fallback ──────────────────────────────────────────────────────────────────
FALLBACK_TICKERS = [
    "AAPL", "TSLA", "NVDA", "META", "MSFT",
    "AMD", "SPY", "QQQ", "AMZN", "GOOGL",
]

# ── Module-level state ────────────────────────────────────────────────────────
CURRENT_TICKERS = list(FALLBACK_TICKERS)
CURRENT_WATCHLIST = [
    {"rank": i + 1, "ticker": t, "change_pct": None, "price_source": "finviz"}
    for i, t in enumerate(FALLBACK_TICKERS)
]
CUSTOM_TICKERS = []          # set via PUT /api/watchlist/custom
LAST_REFRESHED = None

# ── Screener config ───────────────────────────────────────────────────────────
_SCREENER_URLS = [
    "https://finviz.com/screener.ashx?v=111&s=ta_topgainers&f=sh_avgvol_o2m",
    "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&f=sh_avgvol_o2m",
]
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sentiment-scanner/1.0)"}
_TOP_N_PER_URL = 10   # rows to take from each screener URL
_FINAL_CAP = 5        # final watchlist capped at 5 — keeps scans well under 60s
_REFRESH_TTL = 1800   # seconds before a refresh is considered stale (30 min)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _parse_change(raw: str):
    """Parse '142.60%' or '-5.23%' → float, or None on failure."""
    try:
        return round(float(raw.replace("%", "").replace(",", "").strip()), 2)
    except (ValueError, AttributeError):
        return None


def _scrape_rows(url: str, limit: int) -> list:
    """Return list of {ticker, change_pct} dicts from a Finviz screener URL."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    rows = []
    for row in soup.select("tr.styled-row"):
        cells = row.find_all("td")
        # Columns: rank(0), ticker(1), company(2), sector(3), industry(4),
        #          country(5), mktcap(6), pe(7), price(8), change%(9), volume(10)
        if len(cells) >= 10:
            sym = cells[1].get_text(strip=True).upper()
            if sym and sym.isalpha() and 1 <= len(sym) <= 5:
                rows.append({
                    "ticker": sym,
                    "change_pct": _parse_change(cells[9].get_text(strip=True)),
                    "price_source": "finviz",
                })
        if len(rows) >= limit:
            break
    return rows


def get_merged_tickers() -> list:
    """Return CURRENT_TICKERS + CUSTOM_TICKERS deduplicated (custom appended at end)."""
    seen = set(CURRENT_TICKERS)
    extra = [t for t in CUSTOM_TICKERS if t not in seen]
    return list(CURRENT_TICKERS) + extra


# ── Main refresh ──────────────────────────────────────────────────────────────
def refresh_watchlist(force: bool = False) -> list:
    """
    Scrape Finviz screeners, optionally enrich with Yahoo pre-market prices,
    sort descending by change%, and cap to _FINAL_CAP tickers.

    Lazy refresh: skips if called within _REFRESH_TTL seconds of the last
    successful refresh (unless force=True). This prevents cold-start overhead
    on Vercel when multiple requests arrive in quick succession.

    Returns the updated CURRENT_TICKERS list.
    """
    global CURRENT_TICKERS, CURRENT_WATCHLIST, LAST_REFRESHED

    if not force and LAST_REFRESHED:
        age = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(LAST_REFRESHED)).total_seconds()
        if age < _REFRESH_TTL:
            print(f"[watchlist] Skipping refresh — last refresh {age:.0f}s ago (TTL={_REFRESH_TTL}s)")
            return CURRENT_TICKERS

    try:
        # 1. Scrape both presets
        seen = set()
        combined = []
        for url in _SCREENER_URLS:
            try:
                for row in _scrape_rows(url, _TOP_N_PER_URL):
                    if row["ticker"] not in seen:
                        seen.add(row["ticker"])
                        combined.append(row)
            except Exception as exc:
                print(f"[watchlist] Screener error ({url}): {exc}")

        if not combined:
            print("[watchlist] Warning: screeners returned 0 rows — keeping current list")
            return CURRENT_TICKERS

        # 2. If before 10 AM ET, enrich with Yahoo pre-market prices
        if use_premarket_sort():
            tickers = [r["ticker"] for r in combined]
            print(f"[watchlist] Pre-market mode — fetching Yahoo prices for {len(tickers)} tickers…")
            pm_data = fetch_price_changes(tickers)
            for r in combined:
                t = r["ticker"]
                if t in pm_data:
                    r["change_pct"] = pm_data[t]["change_pct"]
                    r["price_source"] = pm_data[t]["source"]   # "premarket" or "regular"
                # else keep Finviz change_pct and price_source="finviz"
        else:
            print("[watchlist] Live mode — using Finviz intraday %")

        # 3. Sort descending by change_pct (None goes last)
        combined.sort(
            key=lambda x: x["change_pct"] if x["change_pct"] is not None else -9999,
            reverse=True,
        )

        # 4. Cap to _FINAL_CAP
        final = combined[:_FINAL_CAP]

        # 5. Update globals
        CURRENT_WATCHLIST = [
            {"rank": i + 1, "ticker": r["ticker"],
             "change_pct": r["change_pct"], "price_source": r["price_source"]}
            for i, r in enumerate(final)
        ]
        CURRENT_TICKERS = [r["ticker"] for r in final]
        LAST_REFRESHED = datetime.datetime.utcnow().isoformat()

        top = final[0]
        print(
            f"[watchlist] Refreshed — {len(final)} tickers, "
            f"top: {top['ticker']} ({top['change_pct']}%, source={top['price_source']})"
        )

    except Exception as exc:
        print(f"[watchlist] Error refreshing: {exc} — keeping current list")

    return CURRENT_TICKERS
