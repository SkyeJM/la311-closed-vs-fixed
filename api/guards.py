"""Guardrails for the public /api/ask (brief section 6D).

- The Anthropic key stays server-side: only this API reads it, and no response includes it.
- A per-IP rate limit (ASK_RATE_LIMIT_PER_HOUR, default 10) on live questions; cached answers
  to the suggested questions don't count.
- A daily spend cap (DAILY_SPEND_CAP_USD), checked before every model call, plus a kill switch
  (ASK_ENABLED=false). The step and token caps live in the agent (ai/agent/loop.py).
- IPs are never stored: rate-limit keys and traces use an HMAC of the IP with IP_HASH_SALT.

Counters live in a Store. MemoryStore is per process, which is right for local use and tests;
a deployment with several instances needs a shared one (UpstashStore), so on Vercel /api/ask
stays off until Upstash credentials and IP_HASH_SALT are set.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from ai.agent.loop import BudgetExceeded


class Store:
    """Counters with expiry. incr adds and returns the new total."""

    def incr(self, key: str, amount: float, ttl_s: int) -> float:
        raise NotImplementedError

    def get(self, key: str) -> float:
        raise NotImplementedError

    shared = False  # do all instances see the same counters?


class MemoryStore(Store):
    def __init__(self):
        self._values: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str, now: float) -> float:
        value, expires = self._values.get(key, (0.0, 0.0))
        return value if expires > now else 0.0

    def incr(self, key: str, amount: float, ttl_s: int) -> float:
        with self._lock:
            now = time.time()
            current = self._live(key, now)
            expires = self._values[key][1] if current else now + ttl_s
            self._values[key] = (current + amount, expires)
            return current + amount

    def get(self, key: str) -> float:
        with self._lock:
            return self._live(key, time.time())


class UpstashStore(Store):
    """Counters in Upstash Redis over its REST API, shared by every instance of the function.

    Each increment is one pipelined request: SET key 0 EX ttl NX creates the counter with its
    expiry if it doesn't exist yet, then INCRBYFLOAT adds to it and keeps that expiry.
    """

    shared = True

    def __init__(self, url: str, token: str, client: httpx.Client | None = None):
        self.url = url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=3.0, headers={"Authorization": f"Bearer {token}"}
        )

    def _pipeline(self, commands: list[list[str]]) -> list:
        response = self.client.post(f"{self.url}/pipeline", json=commands)
        response.raise_for_status()
        results = response.json()
        errors = [r["error"] for r in results if "error" in r]
        if errors:
            raise RuntimeError(f"Upstash: {errors[0]}")
        return [r["result"] for r in results]

    def incr(self, key: str, amount: float, ttl_s: int) -> float:
        _, total = self._pipeline(
            [["SET", key, "0", "EX", str(ttl_s), "NX"], ["INCRBYFLOAT", key, repr(amount)]]
        )
        return float(total)

    def get(self, key: str) -> float:
        (value,) = self._pipeline([["GET", key]])
        return float(value) if value is not None else 0.0


def store_from_env() -> Store:
    """Upstash when its REST credentials are set (Vercel's Marketplace integration sets the
    KV_ names, a manual setup the UPSTASH_ ones); otherwise counters in this process."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    return UpstashStore(url, token) if url and token else MemoryStore()


@dataclass(frozen=True)
class Policy:
    enabled: bool = True
    disabled_reason: str = ""
    rate_limit_per_hour: int = 10
    daily_cap_usd: float = 1.0
    ip_salt: str = ""

    @classmethod
    def from_env(cls, store: Store) -> Policy:
        enabled = os.environ.get("ASK_ENABLED", "true").lower() not in ("false", "0", "no")
        reason = "" if enabled else "The Ask feature is switched off for now."
        salt = os.environ.get("IP_HASH_SALT", "")
        if os.environ.get("VERCEL") and not (store.shared and salt):
            enabled, reason = False, "Ask needs a shared counter store and IP_HASH_SALT here."
        if not os.environ.get("ANTHROPIC_API_KEY"):
            enabled, reason = False, "Ask has no Anthropic API key configured."
        return cls(
            enabled=enabled,
            disabled_reason=reason,
            rate_limit_per_hour=int(os.environ.get("ASK_RATE_LIMIT_PER_HOUR", "10")),
            daily_cap_usd=float(os.environ.get("DAILY_SPEND_CAP_USD", "1.0")),
            # Without a configured salt, a random one: hashes then can't be linked across
            # restarts, which is fine on one local process.
            ip_salt=salt or secrets.token_hex(16),
        )


class StoreUnavailable(RuntimeError):
    """The counter store can't be reached; Ask fails closed rather than run unmetered."""


class Guards:
    def __init__(self, store: Store, policy: Policy):
        self.store = store
        self.policy = policy

    def hash_ip(self, ip: str) -> str:
        digest = hmac.new(self.policy.ip_salt.encode(), ip.encode(), hashlib.sha256)
        return digest.hexdigest()[:16]

    def take_question(self, ip_hash: str) -> tuple[bool, int]:
        """Count a live question against the IP's hourly limit: (allowed, seconds to wait)."""
        hour = int(time.time() // 3600)
        try:
            used = self.store.incr(f"rate:{ip_hash}:{hour}", 1, 3600)
        except Exception as e:
            raise StoreUnavailable("rate-limit counter unavailable") from e
        if used <= self.policy.rate_limit_per_hour:
            return True, 0
        return False, 3600 - int(time.time() % 3600)

    def take_feedback(self, ip_hash: str, limit: int = 30) -> bool:
        hour = int(time.time() // 3600)
        return self.store.incr(f"feedback:{ip_hash}:{hour}", 1, 3600) <= limit

    # The spend guard, in the shape the agent's loop expects (check before, add after).
    def _day_key(self) -> str:
        return f"spend:{datetime.now(UTC).date().isoformat()}"

    def spent_today(self) -> float:
        return self.store.get(self._day_key())

    def check(self) -> None:
        try:
            spent = self.spent_today()
        except Exception as e:
            raise BudgetExceeded(
                "The AI's spend counter can't be reached right now, so Ask is paused. Cached "
                "answers to the suggested questions still work."
            ) from e
        if spent >= self.policy.daily_cap_usd:
            raise BudgetExceeded(
                "Today's AI budget for this demo is used up. Cached answers to the suggested "
                "questions still work, and the budget resets at midnight UTC."
            )

    def add(self, usd: float) -> None:
        try:
            self.store.incr(self._day_key(), usd, 2 * 86400)
        except Exception as e:  # the money is already spent; record the miss, don't fail
            print(f"spend counter update failed: {e!r}", file=sys.stderr)


def client_ip(headers, peer: str | None) -> str:
    """The caller's IP. Behind a proxy that sets it (TRUST_PROXY_HEADERS=true, as on Vercel),
    the first x-forwarded-for entry; otherwise the socket peer."""
    if os.environ.get("TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes"):
        forwarded = headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if headers.get("x-real-ip"):
            return headers["x-real-ip"].strip()
    return peer or "unknown"
