from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, UniqueConstraint
from backend.db.database import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20), nullable=False)        # "reddit" | "stocktwits"
    external_id = Column(String(100), nullable=False)  # reddit post/comment id or stocktwits id
    ticker = Column(String(10), nullable=False, index=True)
    text = Column(Text, nullable=False)
    url = Column(String(500))
    raw_score = Column(Integer, default=0)             # upvotes / likes
    published_at = Column(DateTime, nullable=True)     # original source publish time
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source", "external_id", "ticker", name="uq_post_source_id_ticker"),
    )


class SentimentScore(Base):
    __tablename__ = "sentiment_scores"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String(10), nullable=False, index=True)
    sentiment = Column(String(10), nullable=False)     # "bullish" | "bearish" | "neutral"
    confidence = Column(Float, nullable=False)
    reason = Column(Text)
    scored_at = Column(DateTime, default=datetime.utcnow)


class TickerSummary(Base):
    __tablename__ = "ticker_summary"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    mention_count = Column(Integer, default=0)
    bullish_count = Column(Integer, default=0)
    bearish_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    avg_confidence = Column(Float, default=0.0)
    sentiment_score = Column(Float, default=0.0)  # (bullish - bearish) / total, range -1 to 1
    last_updated = Column(DateTime, default=datetime.utcnow)


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    posts_scraped = Column(Integer, default=0)
    posts_scored = Column(Integer, default=0)
    tickers_found = Column(Integer, default=0)
    error = Column(Text)
