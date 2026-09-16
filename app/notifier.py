"""Telegram Bot API notifier (sendMessage).

The bot token is read from the environment and used only as the Bot API URL
path — it is never logged or written to disk.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .rules import BP_CODES
from .scoring.alerts import CODE_LABEL, CODE_PRIORITY

log = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.telegram.org"


def html_escape(text) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_score_line(match: dict) -> str:
    sets = f"{match.get('sets_p1', 0)}\u2013{match.get('sets_p2', 0)}"
    games = f"{match.get('games_p1', 0)}\u2013{match.get('games_p2', 0)}"
    points = f"{match.get('points_p1', '0')}\u2013{match.get('points_p2', '0')}"
    history = match.get("set_history") or ""
    line = f"Sets {sets} \u00b7 Games {games} \u00b7 <b>{html_escape(points)}</b>"
    if history:
        line += f"\nSets so far: {html_escape(history)}"
    return line


def pick_label(match: dict, triggers: list[str]) -> str:
    """Highest-priority label among the user's hitting triggers / current alerts."""
    alerts = list(match.get("alerts") or [])
    codes: list[str] = []
    for trigger in triggers:
        if trigger == "break-point":
            codes.extend(c for c in alerts if c in BP_CODES)
        elif trigger in alerts:
            codes.append(trigger)
    if not codes:
        codes = list(alerts or triggers)
    if not codes:
        return match.get("alert_label") or "Alert"
    top = max(codes, key=lambda a: CODE_PRIORITY.get(a, 0))
    return CODE_LABEL.get(top, match.get("alert_label") or top)


def format_alert(match: dict, triggers: list[str]) -> str:
    """Build an HTML Telegram message for one rising-edge alert."""
    label = pick_label(match, triggers)
    p1 = html_escape(match.get("p1") or "Player 1")
    p2 = html_escape(match.get("p2") or "Player 2")
    server = match.get("server")
    if server == 1:
        serving = p1
    elif server == 2:
        serving = p2
    else:
        serving = "unknown"

    meta_parts = []
    tour = (match.get("tour") or "").upper()
    if tour and tour != "UNKNOWN":
        meta_parts.append(html_escape(tour))
    if match.get("tournament"):
        meta_parts.append(html_escape(match["tournament"]))
    if match.get("surface"):
        meta_parts.append(html_escape(str(match["surface"]).title()))
    meta = " \u00b7 ".join(meta_parts)

    lines = [f"\U0001f3be <b>{html_escape(label)}</b>"]
    if meta:
        lines.append(meta)
    lines.append("")
    lines.append(f"<b>{p1}</b> vs <b>{p2}</b>")
    lines.append(format_score_line(match))
    lines.append(f"Serving: {serving}")
    if match.get("is_tiebreak"):
        lines.append("Tiebreak in progress")
    win_prob = match.get("win_prob_p1")
    if win_prob is not None:
        lines.append(f"Model P1: {win_prob:.1f}%")
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, token: str, api_base: str = DEFAULT_API_BASE, timeout: float = 10.0):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is empty")
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def format_alert(self, match: dict, triggers: list[str]) -> str:
        return format_alert(match, triggers)

    def send(self, chat_id, text: str, parse_mode: str = "HTML") -> dict:
        """POST sendMessage. Returns the Bot API JSON body. Does not log the token."""
        url = f"{self.api_base}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "tennis-trader-alerts/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            log.warning(
                "Telegram sendMessage failed chat_id=%s http=%s body=%s",
                chat_id,
                exc.code,
                detail[:300],
            )
            raise
        if not body.get("ok"):
            log.warning("Telegram sendMessage rejected chat_id=%s desc=%s", chat_id, body.get("description"))
            raise RuntimeError(body.get("description") or "telegram sendMessage not ok")
        return body


class LogNotifier:
    """Dry-run notifier: formats the same message and logs it instead of sending."""

    def format_alert(self, match: dict, triggers: list[str]) -> str:
        return format_alert(match, triggers)

    def send(self, chat_id, text: str, parse_mode: str = "HTML") -> dict:
        log.info("DRY-RUN telegram chat_id=%s\n%s", chat_id, text)
        return {"ok": True, "result": {"chat_id": chat_id, "dry_run": True}}
