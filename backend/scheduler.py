from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from backend.db.database import SessionLocal
from backend.db.models import Post, SentimentScore, TickerSummary, ScanLog
from backend.scrapers import finviz, yahoo, newsapi
from backend.watchlist import refresh_watchlist
import backend.watchlist as watchlist_module
from backend.analysis.ticker_extractor import extract_ticker_post_pairs
from backend.analysis.sentiment import score_posts

scheduler = BackgroundScheduler()


def run_scan():
    db = SessionLocal()
    log = ScanLog(started_at=datetime.utcnow())
    db.add(log)
    db.commit()

    posts_scraped = 0
    posts_scored = 0
    ticker_post_map: dict = {}

    try:
        # 1. Scrape all sources (auto watchlist + any custom tickers)
        current_tickers = list({*watchlist_module.CURRENT_TICKERS, *watchlist_module.CUSTOM_TICKERS})
        raw_posts = []
        for post in finviz.fetch_posts(current_tickers):
            raw_posts.append(post)
        for post in yahoo.fetch_posts(current_tickers):
            raw_posts.append(post)
        for post in newsapi.fetch_posts(current_tickers):
            raw_posts.append(post)

        # 2. Extract tickers and deduplicate posts against DB
        for ticker, post in extract_ticker_post_pairs(raw_posts):
            exists = (
                db.query(Post)
                .filter_by(source=post["source"], external_id=post["external_id"], ticker=ticker)
                .first()
            )
            if exists:
                continue

            db_post = Post(
                source=post["source"],
                external_id=post["external_id"],
                ticker=ticker,
                text=post["text"],
                url=post.get("url", ""),
                raw_score=post.get("raw_score", 0),
                published_at=post.get("published_at"),
            )
            db.add(db_post)
            db.flush()
            posts_scraped += 1
            post["db_id"] = db_post.id

            if ticker not in ticker_post_map:
                ticker_post_map[ticker] = []
            ticker_post_map[ticker].append(post)

        db.commit()

        # 3. Backfill up to 200 existing unscored posts per cycle (prevents runaway scans)
        BACKFILL_CAP = 200
        scored_ids = {row[0] for row in db.query(SentimentScore.post_id).all()}
        unscored_q = db.query(Post).filter(Post.id.notin_(scored_ids)) if scored_ids else db.query(Post)
        unscored = unscored_q.order_by(Post.id.desc()).limit(BACKFILL_CAP).all()
        for post_row in unscored:
            if post_row.ticker not in ticker_post_map:
                ticker_post_map[post_row.ticker] = []
            ticker_post_map[post_row.ticker].append({
                "db_id": post_row.id,
                "text": post_row.text,
            })

        # 4. Score sentiment per ticker (new + previously unscored)
        for ticker, posts in ticker_post_map.items():
            scores = score_posts(ticker, posts)
            for s in scores:
                if s["post_id"] is None:
                    continue
                db.add(SentimentScore(
                    post_id=s["post_id"],
                    ticker=s["ticker"],
                    sentiment=s["sentiment"],
                    confidence=s["confidence"],
                    reason=s["reason"],
                ))
                posts_scored += 1
        db.commit()

        # 5. Upsert ticker summaries
        _update_ticker_summaries(db, list(ticker_post_map.keys()))

        log.finished_at = datetime.utcnow()
        log.posts_scraped = posts_scraped
        log.posts_scored = posts_scored
        log.tickers_found = len(ticker_post_map)
        db.commit()
        print(f"[scan] Done — {posts_scraped} new posts, {len(ticker_post_map)} tickers")

    except Exception as exc:
        log.error = str(exc)
        log.finished_at = datetime.utcnow()
        db.commit()
        print(f"[scan] Error: {exc}")
    finally:
        db.close()


def _update_ticker_summaries(db, tickers: list):
    for ticker in tickers:
        scores = db.query(SentimentScore).filter_by(ticker=ticker).all()
        if not scores:
            continue

        bullish = sum(1 for s in scores if s.sentiment == "bullish")
        bearish = sum(1 for s in scores if s.sentiment == "bearish")
        neutral = sum(1 for s in scores if s.sentiment == "neutral")
        total = len(scores)
        avg_conf = sum(s.confidence for s in scores) / total
        sent_score = (bullish - bearish) / total if total else 0.0

        summary = db.query(TickerSummary).filter_by(ticker=ticker).first()
        if summary:
            summary.mention_count = total
            summary.bullish_count = bullish
            summary.bearish_count = bearish
            summary.neutral_count = neutral
            summary.avg_confidence = round(avg_conf, 4)
            summary.sentiment_score = round(sent_score, 4)
            summary.last_updated = datetime.utcnow()
        else:
            db.add(TickerSummary(
                ticker=ticker,
                mention_count=total,
                bullish_count=bullish,
                bearish_count=bearish,
                neutral_count=neutral,
                avg_confidence=round(avg_conf, 4),
                sentiment_score=round(sent_score, 4),
            ))


def start_scheduler():
    # Refresh watchlist immediately on startup, then every day at 8:00 AM ET
    refresh_watchlist()
    scheduler.add_job(
        refresh_watchlist,
        "cron",
        hour=8,
        minute=0,
        timezone="America/New_York",
        id="watchlist_refresh",
        replace_existing=True,
    )

    # At 10:00 AM ET switch from pre-market sort to live Finviz %
    scheduler.add_job(
        refresh_watchlist,
        "cron",
        hour=10,
        minute=0,
        timezone="America/New_York",
        id="watchlist_live_switch",
        replace_existing=True,
    )

    # Scan every 5 minutes
    scheduler.add_job(run_scan, "interval", minutes=5, id="scan", replace_existing=True)
    scheduler.start()
    print("[scheduler] Started — watchlist refresh at 8:00 AM ET, live switch at 10:00 AM ET, scan every 5 minutes")
