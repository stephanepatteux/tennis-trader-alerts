"""Environment loading and configuration errors.

Secrets (``LIVE_TENNIS_API_KEY``, ``TELEGRAM_BOT_TOKEN``) are read from the
process environment — never from the repository. A local ``.env`` file is loaded
if present, without overriding variables already set.
"""

from __future__ import annotations

import os
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Load ``KEY=VALUE`` pairs from ``path`` into ``os.environ`` (setdefault)."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default) or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def require_env(name: str, hint: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        extra = f" {hint}" if hint else ""
        raise ConfigError(f"{name} is required.{extra}")
    return value
