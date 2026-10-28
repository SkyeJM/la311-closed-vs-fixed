"""What an Anthropic API call cost, from its usage block.

Prices are USD per million tokens from https://platform.claude.com/docs/en/about-claude/pricing
(checked 2026-10-28). Code labeling uses this for its spend cap, and Phase 4 uses it for
DAILY_SPEND_CAP_USD. Re-check the page when a model or price changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    output: float


PRICES = {
    "claude-haiku-5-5": Price(0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-sonnet-5-5": Price(2.00, 2.50, 4.00, 0.10, 10.00),
    "claude-opus-5-5": Price(4.00, 5.00, 8.00, 0.20, 20.00),
}
# Haiku 5.5 charges more for a request whose prompt (cache reads and writes included) is over
# 100,000 tokens. The other current models price the full context window at one rate.
LONG_PROMPT_TOKENS = {"claude-haiku-5-5": 100_000}
LONG_PROMPT_PRICES = {"claude-haiku-5-5": Price(0.50, 0.625, 1.00, 0.05, 2.50)}


def _tokens(usage, name: str) -> int:
    return getattr(usage, name, None) or 0


def cost_usd(model: str, usage) -> float:
    """Cost of one response; `usage` is the SDK's usage object (or anything with its fields)."""
    if model not in PRICES:
        raise KeyError(f"no price for {model}: add it to ai/pricing.py from the pricing page")
    written = _tokens(usage, "cache_creation_input_tokens")
    read = _tokens(usage, "cache_read_input_tokens")
    fresh = _tokens(usage, "input_tokens")
    price = PRICES[model]
    if model in LONG_PROMPT_TOKENS and written + read + fresh > LONG_PROMPT_TOKENS[model]:
        price = LONG_PROMPT_PRICES[model]
    # The breakdown by TTL appears when a request writes 1-hour cache entries.
    breakdown = getattr(usage, "cache_creation", None)
    written_1h = (getattr(breakdown, "ephemeral_1h_input_tokens", None) or 0) if breakdown else 0
    dollars = (
        fresh * price.input
        + (written - written_1h) * price.cache_write_5m
        + written_1h * price.cache_write_1h
        + read * price.cache_read
        + _tokens(usage, "output_tokens") * price.output
    )
    return dollars / 1_000_000
