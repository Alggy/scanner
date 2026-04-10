from __future__ import annotations

import json
import os
from typing import Any
import requests as _requests

BATCH_SIZE = 15  # posts per Claude API call (used by per-ticker fallback)

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"


def _call_claude(prompt: str, max_tokens: int = 1024) -> str:
    """Call Anthropic API via requests (avoids httpx issues on Vercel)."""
    api_key = os.environ["ANTHROPIC_API_KEY"].strip()
    resp = _requests.post(
        _ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": _MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def _build_prompt(ticker: str, posts: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(posts))
    return (
        f"You are a financial sentiment analyst. Analyze the following {len(posts)} social media "
        f"posts that mention the stock ticker ${ticker}.\n\n"
        f"Posts:\n{numbered}\n\n"
        f"For EACH post (in order), return a JSON array where each element has:\n"
        f'  "sentiment": "bullish", "bearish", or "neutral"\n'
        f'  "confidence": a float 0.0–1.0 indicating how confident you are\n'
        f'  "reason": a brief one-sentence explanation\n\n'
        f"Return ONLY valid JSON — no markdown, no extra text. Example:\n"
        f'[{{"sentiment":"bullish","confidence":0.85,"reason":"User expects strong earnings."}}]'
    )


def _build_multi_ticker_prompt(entries: list[dict]) -> str:
    """Build a prompt for scoring posts across multiple tickers in one call.

    entries: [{"ticker": str, "text": str, "idx": int}]
    Returns prompt expecting a JSON array of length len(entries).
    """
    lines = "\n".join(
        f"{e['idx']+1}. [{e['ticker']}] {e['text'][:300]}" for e in entries
    )
    return (
        f"You are a financial sentiment analyst. Score each post below.\n"
        f"Each post is labeled [TICKER] followed by its text.\n\n"
        f"Posts:\n{lines}\n\n"
        f"Return a JSON array with exactly {len(entries)} elements (one per post, in order).\n"
        f"Each element: {{\"sentiment\": \"bullish\"|\"bearish\"|\"neutral\", "
        f"\"confidence\": 0.0-1.0, \"reason\": \"one sentence\"}}\n"
        f"Return ONLY valid JSON — no markdown, no extra text."
    )


def score_all_tickers(ticker_post_map: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """
    Score posts for ALL tickers in a single Claude API call.
    Much faster than one call per ticker.

    ticker_post_map: {ticker: [{"db_id": int, "text": str}, ...]}
    Returns list of dicts with keys: post_id, ticker, sentiment, confidence, reason.
    """
    # Flatten all posts into a single indexed list
    entries: list[dict] = []
    for ticker, posts in ticker_post_map.items():
        for post in posts:
            entries.append({
                "idx": len(entries),
                "ticker": ticker,
                "db_id": post.get("db_id"),
                "text": post.get("text", ""),
            })

    if not entries:
        return []

    results: list[dict[str, Any]] = []

    # Process in chunks of 50 to stay within token limits
    CHUNK = 50
    for start in range(0, len(entries), CHUNK):
        chunk = entries[start : start + CHUNK]
        # Re-index within chunk
        for i, e in enumerate(chunk):
            e["idx"] = i

        prompt = _build_multi_ticker_prompt(chunk)
        try:
            raw = _call_claude(prompt, max_tokens=1024)
            scores = json.loads(raw)

            for i, score in enumerate(scores):
                if i >= len(chunk):
                    break
                entry = chunk[i]
                results.append({
                    "post_id": entry["db_id"],
                    "ticker": entry["ticker"],
                    "sentiment": score.get("sentiment", "neutral"),
                    "confidence": float(score.get("confidence", 0.5)),
                    "reason": score.get("reason", ""),
                })
        except json.JSONDecodeError as exc:
            print(f"[sentiment] JSON parse error (multi-ticker chunk {start}): {exc}")
            for entry in chunk:
                results.append({
                    "post_id": entry["db_id"],
                    "ticker": entry["ticker"],
                    "sentiment": "neutral",
                    "confidence": 0.0,
                    "reason": "parse error",
                })
        except Exception as exc:
            # Re-raise so run_scan() can capture it in log.error
            raise RuntimeError(f"[sentiment] Claude API error (multi-ticker chunk {start}): {exc}") from exc

    return results


def score_posts(ticker: str, posts: list[dict]) -> list[dict[str, Any]]:
    """
    Score a list of post dicts for a given ticker.
    Returns list of dicts with keys: post_id, ticker, sentiment, confidence, reason.
    """
    results = []
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        texts = [p["text"] for p in batch]

        try:
            raw = _call_claude(_build_prompt(ticker, texts), max_tokens=1024)
            scores = json.loads(raw)

            for j, score in enumerate(scores):
                if j >= len(batch):
                    break
                results.append({
                    "post_id": batch[j].get("db_id"),
                    "ticker": ticker,
                    "sentiment": score.get("sentiment", "neutral"),
                    "confidence": float(score.get("confidence", 0.5)),
                    "reason": score.get("reason", ""),
                })
        except json.JSONDecodeError as exc:
            print(f"[sentiment] JSON parse error for {ticker} batch {i}: {exc}")
            # Fallback: mark all in batch as neutral
            for post in batch:
                results.append({
                    "post_id": post.get("db_id"),
                    "ticker": ticker,
                    "sentiment": "neutral",
                    "confidence": 0.0,
                    "reason": "parse error",
                })
        except Exception as exc:
            print(f"[sentiment] Claude API error for {ticker}: {exc}")

    return results
