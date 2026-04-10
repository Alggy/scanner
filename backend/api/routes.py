from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.database import get_db
from backend.db.models import TickerSummary, Post, SentimentScore, ScanLog
import backend.watchlist as watchlist_module

router = APIRouter(prefix="/api")


# ── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist")
def get_watchlist():
    """Current dynamic watchlist — top movers sorted by change % descending."""
    return {
        "tickers": watchlist_module.CURRENT_WATCHLIST,
        "custom_tickers": watchlist_module.CUSTOM_TICKERS,
        "last_refreshed": watchlist_module.LAST_REFRESHED,
        "count": len(watchlist_module.CURRENT_WATCHLIST),
    }


@router.put("/watchlist/custom")
def set_custom_watchlist(body: dict):
    """Replace the in-memory custom ticker list (max 10)."""
    raw = body.get("tickers", [])
    tickers = [t.upper().strip() for t in raw if isinstance(t, str) and t.strip()][:10]
    watchlist_module.CUSTOM_TICKERS = tickers
    return {"custom_tickers": watchlist_module.CUSTOM_TICKERS}


# ── Ticker search (autocomplete) ──────────────────────────────────────────────

@router.get("/search/tickers")
def search_tickers(q: str = Query("", min_length=1)):
    """Return up to 20 ticker symbols starting with `q` (case-insensitive)."""
    from backend.analysis.ticker_extractor import _load_valid_tickers
    q_upper = q.upper().strip()
    if not q_upper:
        return {"results": []}
    all_tickers = _load_valid_tickers()   # frozenset, lru_cache'd
    matches = sorted(t for t in all_tickers if t.startswith(q_upper))[:20]
    return {"results": matches}


# ── Prices ────────────────────────────────────────────────────────────────────

@router.get("/prices")
def get_prices():
    """
    Fetch pre-market (or regular) price change % for all current watchlist tickers.
    Uses Yahoo Finance Chart API — free, no key required.
    """
    from backend.scrapers.prices import fetch_price_changes
    tickers = watchlist_module.CURRENT_TICKERS
    if not tickers:
        return {}
    return fetch_price_changes(tickers)


@router.get("/prices/custom")
def get_custom_prices():
    """Fetch price change % for the user's custom tickers."""
    from backend.scrapers.prices import fetch_price_changes
    tickers = watchlist_module.CUSTOM_TICKERS
    if not tickers:
        return {}
    return fetch_price_changes(tickers)


# ── Tickers table ─────────────────────────────────────────────────────────────

@router.get("/tickers")
def get_tickers(
    window: str = Query("1h", regex="^(1h|4h|1d)$"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Top tickers sorted by a weighted sentiment score * mention_count."""
    cutoff = {
        "1h": datetime.utcnow() - timedelta(hours=1),
        "4h": datetime.utcnow() - timedelta(hours=4),
        "1d": datetime.utcnow() - timedelta(days=1),
    }[window]

    summaries = (
        db.query(TickerSummary)
        .filter(TickerSummary.last_updated >= cutoff)
        .order_by(desc(TickerSummary.mention_count))
        .limit(limit)
        .all()
    )

    return [
        {
            "ticker": s.ticker,
            "mention_count": s.mention_count,
            "bullish_count": s.bullish_count,
            "bearish_count": s.bearish_count,
            "neutral_count": s.neutral_count,
            "bullish_pct": round(s.bullish_count / s.mention_count * 100, 1) if s.mention_count else 0,
            "bearish_pct": round(s.bearish_count / s.mention_count * 100, 1) if s.mention_count else 0,
            "sentiment_score": s.sentiment_score,
            "avg_confidence": s.avg_confidence,
            "last_updated": s.last_updated.isoformat() if s.last_updated else None,
        }
        for s in summaries
    ]


@router.get("/tickers/{ticker}")
def get_ticker_detail(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Detail view: recent posts with sentiment for a given ticker."""
    ticker = ticker.upper()
    summary = db.query(TickerSummary).filter_by(ticker=ticker).first()

    posts = (
        db.query(Post, SentimentScore)
        .join(SentimentScore, Post.id == SentimentScore.post_id)
        .filter(Post.ticker == ticker)
        .order_by(desc(Post.created_at))
        .limit(limit)
        .all()
    )

    return {
        "ticker": ticker,
        "summary": {
            "mention_count": summary.mention_count if summary else 0,
            "bullish_count": summary.bullish_count if summary else 0,
            "bearish_count": summary.bearish_count if summary else 0,
            "neutral_count": summary.neutral_count if summary else 0,
            "sentiment_score": summary.sentiment_score if summary else 0,
            "avg_confidence": summary.avg_confidence if summary else 0,
        } if summary else {},
        "posts": [
            {
                "id": p.id,
                "source": p.source,
                "text": p.text[:300],
                "url": p.url,
                "raw_score": p.raw_score,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "created_at": p.created_at.isoformat(),
                "sentiment": s.sentiment,
                "confidence": s.confidence,
                "reason": s.reason,
            }
            for p, s in posts
        ],
    }


# ── Strategy ──────────────────────────────────────────────────────────────────

@router.get("/tickers/{ticker}/strategy")
def get_ticker_strategy(
    ticker: str,
    db: Session = Depends(get_db),
):
    """
    Return a day-trading strategy recommendation for a ticker.
    Generated by Claude Haiku; results are cached in memory until server restart.
    """
    ticker = ticker.upper()
    from backend.strategy import get_strategy

    summary_row = db.query(TickerSummary).filter_by(ticker=ticker).first()
    posts_rows = (
        db.query(Post, SentimentScore)
        .join(SentimentScore, Post.id == SentimentScore.post_id)
        .filter(Post.ticker == ticker)
        .order_by(desc(Post.created_at))
        .limit(10)
        .all()
    )

    summary = {
        "bullish_count": summary_row.bullish_count if summary_row else 0,
        "bearish_count": summary_row.bearish_count if summary_row else 0,
        "neutral_count": summary_row.neutral_count if summary_row else 0,
        "sentiment_score": summary_row.sentiment_score if summary_row else 0,
    }
    posts_list = [{"sentiment": s.sentiment, "text": p.text} for p, s in posts_rows]

    try:
        return get_strategy(ticker, summary, posts_list)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Scan status / trigger ─────────────────────────────────────────────────────

@router.get("/scan/status")
def get_scan_status(db: Session = Depends(get_db)):
    """Last scan metadata + trigger info."""
    last = db.query(ScanLog).order_by(desc(ScanLog.started_at)).first()
    total_tickers = db.query(TickerSummary).count()
    total_posts = db.query(Post).count()

    return {
        "total_tickers_tracked": total_tickers,
        "total_posts_in_db": total_posts,
        "last_scan": {
            "started_at": last.started_at.isoformat() if last else None,
            "finished_at": last.finished_at.isoformat() if last and last.finished_at else None,
            "posts_scraped": last.posts_scraped if last else 0,
            "posts_scored": last.posts_scored if last else 0,
            "tickers_found": last.tickers_found if last else 0,
            "error": last.error if last else None,
        } if last else None,
    }


@router.post("/scan/trigger")
def trigger_scan():
    """Manually trigger a scan (runs in background thread)."""
    import threading
    from backend.scheduler import run_scan
    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    return {"status": "scan triggered"}
