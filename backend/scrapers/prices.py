"""
Yahoo Finance Chart API — free pre-market / regular price data.
No API key required.

fetch_price_changes(tickers) -> dict
  {
    "AAPL": {
      "change_pct": -0.42,
      "price": 182.30,
      "prev_close": 183.07,
      "source": "premarket"   # or "regular"
    },
    ...
  }
"""
import time
import requests

_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch_price_changes(tickers: list) -> dict:
    """
    Fetch pre-market (or regular-market) price change % for each ticker.
    Skips tickers that fail with a warning; never raises.
    """
    results = {}
    for ticker in tickers:
        try:
            resp = requests.get(
                _CHART_URL.format(ticker=ticker),
                params={
                    "interval": "1d",
                    "range": "1d",
                    "prePost": "true",
                    "includePrePost": "true",
                },
                headers=_HEADERS,
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            chart = data.get("chart", {})
            result_list = chart.get("result") or []
            if not result_list:
                continue

            meta = result_list[0].get("meta", {})
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            pre_price = meta.get("preMarketPrice")
            reg_price = meta.get("regularMarketPrice")

            if prev_close and prev_close > 0:
                if pre_price and pre_price > 0:
                    change_pct = round((pre_price - prev_close) / prev_close * 100, 2)
                    results[ticker] = {
                        "change_pct": change_pct,
                        "price": pre_price,
                        "prev_close": prev_close,
                        "source": "premarket",
                    }
                elif reg_price and reg_price > 0:
                    change_pct = round((reg_price - prev_close) / prev_close * 100, 2)
                    results[ticker] = {
                        "change_pct": change_pct,
                        "price": reg_price,
                        "prev_close": prev_close,
                        "source": "regular",
                    }

        except Exception as exc:
            print(f"[prices] {ticker}: {exc}")

        time.sleep(0.15)  # gentle rate limiting

    return results
