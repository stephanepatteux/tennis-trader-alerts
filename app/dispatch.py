"""Rising-edge de-dup, per-user rate limiting, and alert dispatch."""

from __future__ import annotations

import logging
import time
from collections import deque

from .notifier import TelegramNotifier
from .rules import RulesStore

log = logging.getLogger(__name__)


class RisingEdgeDeduper:
    """Remember the last alert-code set per match so only *new* codes fire."""

    def __init__(self):
        self._prev: dict = {}

    def update(self, match_id, alerts) -> tuple[frozenset, frozenset]:
        current = frozenset(alerts or ())
        prev = self._prev.get(match_id, frozenset())
        self._prev[match_id] = current
        return prev, current

    def previous(self, match_id) -> frozenset:
        return self._prev.get(match_id, frozenset())


class RateLimiter:
    """Sliding-window limiter: at most ``max_events`` per ``window_s`` for a key."""

    def __init__(self, max_events: int, window_s: float, time_fn=time.monotonic):
        self.max_events = max_events
        self.window_s = window_s
        self._time = time_fn
        self._hits: dict[str, deque] = {}

    def allow(self, key) -> bool:
        now = self._time()
        q = self._hits.setdefault(str(key), deque())
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True


class Dispatcher:
    """Consume a mapped match, apply rules, de-dup, rate-limit, and notify."""

    def __init__(
        self,
        rules: RulesStore,
        notifier: TelegramNotifier,
        rate_limiter: RateLimiter | None = None,
        deduper: RisingEdgeDeduper | None = None,
    ):
        self.rules = rules
        self.notifier = notifier
        self.rate_limiter = rate_limiter or RateLimiter(max_events=20, window_s=60.0)
        self.deduper = deduper or RisingEdgeDeduper()

    def handle(self, match: dict) -> list[dict]:
        """Process one match update. Returns a list of result dicts (for tests)."""
        if not match or match.get("id") is None:
            return []
        match_id = match["id"]
        prev, current = self.deduper.update(match_id, match.get("alerts") or [])

        results: list[dict] = []
        for user in self.rules.users():
            if not user.enabled:
                continue
            if not user.matches_filters(match):
                continue
            hits = user.matching_triggers(prev, current)
            if not hits:
                continue
            if not self.rate_limiter.allow(user.chat_id):
                log.info(
                    "rate-limited chat_id=%s match_id=%s triggers=%s",
                    user.chat_id,
                    match_id,
                    hits,
                )
                results.append(
                    {
                        "status": "rate_limited",
                        "chat_id": user.chat_id,
                        "match_id": match_id,
                        "triggers": hits,
                    }
                )
                continue
            text = self.notifier.format_alert(match, hits)
            try:
                self.notifier.send(user.chat_id, text)
            except Exception:
                log.exception(
                    "notify failed chat_id=%s match_id=%s", user.chat_id, match_id
                )
                results.append(
                    {
                        "status": "error",
                        "chat_id": user.chat_id,
                        "match_id": match_id,
                        "triggers": hits,
                    }
                )
                continue
            log.info(
                "sent chat_id=%s match_id=%s triggers=%s",
                user.chat_id,
                match_id,
                hits,
            )
            results.append(
                {
                    "status": "sent",
                    "chat_id": user.chat_id,
                    "match_id": match_id,
                    "triggers": hits,
                    "text": text,
                }
            )
        return results
