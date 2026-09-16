"""Per-user alert rules: which triggers fire, and which matches to watch.

A user is a Telegram ``chat_id`` plus:

- **triggers** — ``0-40``, ``15-40``, ``30-40``, ``break-point`` (any BP),
  ``deuce``, ``tiebreak``
- **filters** — tour (atp/wta), surface (clay/hard/grass), player watchlist

Empty filter lists mean "no restriction". Rules are loaded from a JSON file
(``RULES_PATH``) when it exists; otherwise a single user is bootstrapped from
``TELEGRAM_CHAT_ID`` and the ``ALERT_*`` env vars.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, env_csv

log = logging.getLogger(__name__)

VALID_TRIGGERS = (
    "0-40",
    "15-40",
    "30-40",
    "break-point",  # any break point, including ad-break
    "deuce",
    "tiebreak",
)

# Codes that count as a break-point situation for the "any BP" trigger.
BP_CODES = frozenset({"0-40", "15-40", "30-40", "ad-break", "break-point"})

DEFAULT_TRIGGERS = list(VALID_TRIGGERS)


def _norm_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    return [str(v).strip().lower() for v in values if str(v).strip()]


@dataclass
class UserRule:
    chat_id: str
    enabled: bool = True
    name: str = ""
    triggers: list[str] = field(default_factory=lambda: list(DEFAULT_TRIGGERS))
    tours: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.chat_id = str(self.chat_id).strip()
        self.triggers = [t for t in _norm_list(self.triggers) if t in VALID_TRIGGERS]
        # Preserve original watchlist casing for display; match case-insensitively.
        self.tours = _norm_list(self.tours)
        self.surfaces = _norm_list(self.surfaces)
        if isinstance(self.watchlist, str):
            self.watchlist = [p.strip() for p in self.watchlist.split(",") if p.strip()]
        else:
            self.watchlist = [
                str(w).strip() for w in (self.watchlist or []) if str(w).strip()
            ]
        if not self.triggers:
            self.triggers = list(DEFAULT_TRIGGERS)

    def matches_filters(self, match: dict) -> bool:
        """Return True if this match passes the user's tour/surface/watchlist filters."""
        if self.tours:
            tour = (match.get("tour") or "").lower()
            if tour not in self.tours:
                return False
        if self.surfaces:
            surface = (match.get("surface") or "").lower()
            if surface not in self.surfaces:
                return False
        if self.watchlist:
            p1 = (match.get("p1") or "").lower()
            p2 = (match.get("p2") or "").lower()
            needles = [w.lower() for w in self.watchlist if w]
            if not any(n in p1 or n in p2 for n in needles):
                return False
        return True

    def matching_triggers(self, prev: frozenset, current: frozenset) -> list[str]:
        """Rising-edge trigger hits for this user given previous/current alert codes."""
        hits: list[str] = []
        for trigger in self.triggers:
            if trigger == "break-point":
                was_bp = bool(prev & BP_CODES)
                is_bp = bool(current & BP_CODES)
                if is_bp and not was_bp:
                    hits.append(trigger)
            elif trigger in current and trigger not in prev:
                hits.append(trigger)
        return hits


class RulesStore:
    """JSON file of users, with optional env-var bootstrap and mtime reload."""

    def __init__(self, users: list[UserRule], path: Path | None = None):
        self._users = users
        self.path = path
        self._mtime = path.stat().st_mtime if path and path.is_file() else None

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "RulesStore":
        rules_path = Path(path or os.environ.get("RULES_PATH", "data/rules.json"))
        if rules_path.is_file():
            return cls._from_file(rules_path)
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not chat_id:
            raise ConfigError(
                "No rules file and TELEGRAM_CHAT_ID is not set. "
                "Copy data/rules.example.json to data/rules.json, or set TELEGRAM_CHAT_ID."
            )
        user = UserRule(
            chat_id=chat_id,
            name=os.environ.get("TELEGRAM_USER_NAME", "default"),
            triggers=env_csv("ALERT_TRIGGERS", ",".join(DEFAULT_TRIGGERS)),
            tours=env_csv("ALERT_TOURS"),
            surfaces=env_csv("ALERT_SURFACES"),
            watchlist=env_csv("ALERT_WATCHLIST"),
        )
        log.info("Loaded 1 user from environment (chat_id=%s)", user.chat_id)
        return cls([user], path=None)

    @classmethod
    def _from_file(cls, path: Path) -> "RulesStore":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("users", raw if isinstance(raw, list) else [])
        users = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("chat_id"):
                continue
            users.append(
                UserRule(
                    chat_id=row["chat_id"],
                    enabled=bool(row.get("enabled", True)),
                    name=str(row.get("name") or ""),
                    triggers=row.get("triggers") or list(DEFAULT_TRIGGERS),
                    tours=row.get("tours") or [],
                    surfaces=row.get("surfaces") or [],
                    watchlist=row.get("watchlist") or [],
                )
            )
        if not users:
            raise ConfigError(f"No users with chat_id found in {path}")
        log.info("Loaded %d user(s) from %s", len(users), path)
        return cls(users, path=path)

    def users(self) -> list[UserRule]:
        return list(self._users)

    def maybe_reload(self) -> bool:
        """Reload from disk if the file's mtime changed. Returns True if reloaded."""
        if self.path is None or not self.path.is_file():
            return False
        mtime = self.path.stat().st_mtime
        if self._mtime is not None and mtime <= self._mtime:
            return False
        try:
            fresh = self._from_file(self.path)
        except (OSError, ValueError, ConfigError) as exc:
            log.warning("Failed to reload rules from %s: %s", self.path, exc)
            return False
        self._users = fresh._users
        self._mtime = mtime
        return True
