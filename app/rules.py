"""Per-user alert rules: which triggers fire, and which matches to watch.

A user is a Telegram ``chat_id`` plus:

- **triggers** — ``0-40``, ``15-40``, ``30-40``, ``break-point`` (any BP),
  ``deuce``, ``tiebreak``
- **filters** — tour (atp/wta), surface (clay/hard/grass), player watchlist

Empty tour/surface/watchlist lists mean "no restriction". An empty ``triggers``
list means nothing fires (the user turned every trigger off). Missing triggers
in a JSON row still default to all of them.

Rules are loaded from ``RULES_PATH``. The Telegram menu writes the same file.
If the file is missing, a single user can be bootstrapped from ``TELEGRAM_CHAT_ID``.
Users who open the bot with /start are created automatically.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .config import env_csv

log = logging.getLogger(__name__)

VALID_TRIGGERS = (
    "0-40",
    "15-40",
    "30-40",
    "break-point",  # any break point, including ad-break
    "deuce",
    "tiebreak",
)

TOURS = ("atp", "wta")
SURFACES = ("clay", "hard", "grass")

# Codes that count as a break-point situation for the "any BP" trigger.
BP_CODES = frozenset({"0-40", "15-40", "30-40", "ad-break", "break-point"})

DEFAULT_TRIGGERS = list(VALID_TRIGGERS)


def _norm_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    return [str(v).strip().lower() for v in values if str(v).strip()]


def toggle_subset(current: list[str], value: str, universe: tuple[str, ...]) -> list[str]:
    """Toggle one value in a multi-select where empty means 'all of universe'."""
    if value not in universe:
        return list(current)
    selected = set(current) if current else set(universe)
    if value in selected:
        selected.discard(value)
    else:
        selected.add(value)
    if not selected or selected == set(universe):
        return []
    return [item for item in universe if item in selected]


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
        self.tours = [t for t in _norm_list(self.tours) if t in TOURS]
        self.surfaces = [s for s in _norm_list(self.surfaces) if s in SURFACES]
        if isinstance(self.watchlist, str):
            self.watchlist = [p.strip() for p in self.watchlist.split(",") if p.strip()]
        else:
            self.watchlist = [
                str(w).strip() for w in (self.watchlist or []) if str(w).strip()
            ]

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "enabled": self.enabled,
            "name": self.name,
            "triggers": list(self.triggers),
            "tours": list(self.tours),
            "surfaces": list(self.surfaces),
            "watchlist": list(self.watchlist),
        }

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

    def toggle_trigger(self, code: str) -> None:
        if code not in VALID_TRIGGERS:
            return
        if code in self.triggers:
            self.triggers = [t for t in self.triggers if t != code]
        else:
            have = set(self.triggers) | {code}
            self.triggers = [t for t in VALID_TRIGGERS if t in have]


class RulesStore:
    """JSON file of users, with optional env-var bootstrap, bot writes, and mtime reload."""

    def __init__(self, users: list[UserRule], path: Path | None = None):
        self._users = users
        self.path = Path(path) if path is not None else None
        self._mtime = (
            self.path.stat().st_mtime if self.path and self.path.is_file() else None
        )
        self._lock = threading.RLock()

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "RulesStore":
        rules_path = Path(path or os.environ.get("RULES_PATH", "data/rules.json"))
        if rules_path.is_file():
            return cls._from_file(rules_path)
        users = []
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if chat_id:
            users.append(
                UserRule(
                    chat_id=chat_id,
                    name=os.environ.get("TELEGRAM_USER_NAME", "default"),
                    triggers=env_csv("ALERT_TRIGGERS", ",".join(DEFAULT_TRIGGERS)),
                    tours=env_csv("ALERT_TOURS"),
                    surfaces=env_csv("ALERT_SURFACES"),
                    watchlist=env_csv("ALERT_WATCHLIST"),
                )
            )
            log.info("Loaded 1 user from environment (chat_id=%s)", chat_id)
        else:
            log.info(
                "No rules file yet; users will be created from the Telegram menu (/start)"
            )
        return cls(users, path=rules_path)

    @classmethod
    def _from_file(cls, path: Path) -> "RulesStore":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("users", raw if isinstance(raw, list) else [])
        users = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("chat_id"):
                continue
            if "triggers" not in row or row.get("triggers") is None:
                triggers = list(DEFAULT_TRIGGERS)
            else:
                triggers = row.get("triggers") or []
            users.append(
                UserRule(
                    chat_id=row["chat_id"],
                    enabled=bool(row.get("enabled", True)),
                    name=str(row.get("name") or ""),
                    triggers=triggers,
                    tours=row.get("tours") or [],
                    surfaces=row.get("surfaces") or [],
                    watchlist=row.get("watchlist") or [],
                )
            )
        log.info("Loaded %d user(s) from %s", len(users), path)
        return cls(users, path=path)

    def users(self) -> list[UserRule]:
        with self._lock:
            return list(self._users)

    def get(self, chat_id) -> UserRule | None:
        key = str(chat_id).strip()
        with self._lock:
            for user in self._users:
                if user.chat_id == key:
                    return user
        return None

    def get_or_create(self, chat_id, name: str = "") -> UserRule:
        key = str(chat_id).strip()
        with self._lock:
            for user in self._users:
                if user.chat_id == key:
                    if name and not user.name:
                        user.name = name
                        self._save_unlocked()
                    return user
            user = UserRule(chat_id=key, name=name or "")
            self._users.append(user)
            self._save_unlocked()
            log.info("Enrolled Telegram chat_id=%s", key)
            return user

    def save(self) -> None:
        with self._lock:
            self._save_unlocked()

    def mutate(self, chat_id, mutator) -> UserRule:
        """Apply ``mutator(user)`` and persist. Creates the user if needed."""
        with self._lock:
            user = None
            key = str(chat_id).strip()
            for existing in self._users:
                if existing.chat_id == key:
                    user = existing
                    break
            if user is None:
                user = UserRule(chat_id=key)
                self._users.append(user)
            mutator(user)
            self._save_unlocked()
            return user

    def _save_unlocked(self) -> None:
        if self.path is None:
            self.path = Path(os.environ.get("RULES_PATH", "data/rules.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"users": [u.to_dict() for u in self._users]}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        self._mtime = self.path.stat().st_mtime

    def maybe_reload(self) -> bool:
        """Reload from disk if the file's mtime changed. Returns True if reloaded."""
        with self._lock:
            if self.path is None or not self.path.is_file():
                return False
            mtime = self.path.stat().st_mtime
            if self._mtime is not None and mtime <= self._mtime:
                return False
            try:
                fresh = self._from_file(self.path)
            except (OSError, ValueError) as exc:
                log.warning("Failed to reload rules from %s: %s", self.path, exc)
                return False
            self._users = fresh._users
            self._mtime = mtime
            return True
