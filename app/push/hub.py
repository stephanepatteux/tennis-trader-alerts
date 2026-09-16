"""In-memory pub/sub hub between the Ultra push source and the alert worker.

A single source thread calls :meth:`publish` on every score commit; the worker
subscribes and receives each updated match. The hub also keeps the latest state
per match so score-only frames can reuse previously-seen static fields.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone


class PushHub:
    def __init__(self, source_name: str = "unknown"):
        self.source_name = source_name
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()
        self._state: dict = {}  # match_id -> match dict
        self._updated_at = None

    # -- producer side ----------------------------------------------------
    def publish(self, match: dict) -> None:
        if not match or match.get("id") is None:
            return
        with self._lock:
            self._state[match["id"]] = match
            self._updated_at = datetime.now(timezone.utc).isoformat()
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(match)
            except queue.Full:
                pass  # slow consumer; it will catch up on its next state anyway

    def publish_many(self, matches) -> None:
        for m in matches:
            self.publish(m)

    # -- consumer side ----------------------------------------------------
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def snapshot(self) -> dict:
        with self._lock:
            matches = list(self._state.values())
            updated = self._updated_at
        return {
            "matches": matches,
            "updated_at": updated,
            "alert_count": sum(1 for m in matches if m.get("alert_priority")),
            "source": self.source_name,
        }

    def static_for(self, match_id) -> dict:
        """Previously-known static fields for a match (for score-only frames)."""
        with self._lock:
            m = self._state.get(match_id)
        if not m:
            return {}
        return {
            "p1": m.get("p1"),
            "p2": m.get("p2"),
            "tour": m.get("tour"),
            "tournament": m.get("tournament"),
            "surface": m.get("surface"),
            "format": m.get("format"),
            "is_doubles": m.get("is_doubles"),
        }
