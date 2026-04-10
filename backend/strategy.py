"""
Day-trading strategy recommendations via Claude Haiku.
Results are cached in memory per ticker (cleared on restart).
"""
import json
import os

import requests as _requests

_strategy_cache = {}

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _call_claude(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 350) -> str:
    """Call Anthropic API via requests (avoids httpx issues on Vercel)."""
    resp = _requests.post(
        _ANTHROPIC_URL,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"].strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def get_strategy(ticker, summary, posts):
    """
    ticker  — str, e.g. "NVDA"
    summary — dict with bullish_count, bearish_count, neutral_count, sentiment_score
    posts   — list of dicts with keys: sentiment, text

    Returns dict:
      { action, rationale, risk_level, entry_signal, exit_signal }
    Raises on API failure (caller should handle).
    """
    if ticker in _strategy_cache:
        return _strategy_cache[ticker]

    total = (summary.get("bullish_count", 0)
             + summary.get("bearish_count", 0)
             + summary.get("neutral_count", 0))
    post_lines = "\n".join(
        f"- [{p.get('sentiment','?')}] {str(p.get('text',''))[:150]}"
        for p in posts[:10]
    )

    prompt = f"""You are a day trading analyst. Analyze the social media sentiment for ${ticker} and recommend a day trading strategy.

Sentiment summary ({total} posts analyzed):
- Bullish: {summary.get('bullish_count', 0)}
- Bearish: {summary.get('bearish_count', 0)}
- Neutral:  {summary.get('neutral_count', 0)}
- Score:    {summary.get('sentiment_score', 0):.2f}  (range -1.0 to +1.0)

Recent posts:
{post_lines if post_lines else "(no posts available)"}

Respond ONLY with valid JSON — no explanation, no markdown, no code fences.
Format:
{{
  "action": "BUY" | "SELL" | "WAIT",
  "rationale": "One or two sentence explanation.",
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "entry_signal": "Brief entry condition.",
  "exit_signal": "Brief exit / stop-loss condition."
}}"""

    raw = _call_claude(prompt, max_tokens=350)

    # Strip markdown code fences if model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = json.loads(raw)

    # Normalise keys
    result["action"] = result.get("action", "WAIT").upper()
    result["risk_level"] = result.get("risk_level", "MEDIUM").upper()

    _strategy_cache[ticker] = result
    return result


def clear_cache(ticker=None):
    """Clear cached strategy for one ticker, or all if ticker is None."""
    if ticker:
        _strategy_cache.pop(ticker, None)
    else:
        _strategy_cache.clear()
