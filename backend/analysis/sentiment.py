from __future__ import annotations

import json
import os
from typing import Any
import anthropic

BATCH_SIZE = 15  # posts per Claude API call

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


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


def score_posts(ticker: str, posts: list[dict]) -> list[dict[str, Any]]:
    """
    Score a list of post dicts for a given ticker.
    Returns list of dicts with keys: post_id, ticker, sentiment, confidence, reason.
    """
    results = []
    client = _get_client()

    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        texts = [p["text"] for p in batch]

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",  # fast + cheap for bulk scoring
                max_tokens=1024,
                messages=[{"role": "user", "content": _build_prompt(ticker, texts)}],
            )
            raw = message.content[0].text.strip()
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
