"""Break-point / score alerts for Tennis Trader Alerts.

Ported from live-tennis-scoreboard so the strategy filters — 0-40, 15-40, 30-40,
any break point, deuce, tiebreak — mean exactly the same thing. An alert only
fires when the *returner* (non-server) is ahead in the game, because that is the
situation a Betfair trader reacts to: the serve is under threat.

These are score signals, not tips.
"""

from __future__ import annotations

# Map a displayed point to a rank so we can reason about game states.
# Advantage is represented as "AD"/"A"; anything numeric (tiebreaks) is handled
# separately by the caller.
_POINT_RANK = {"0": 0, "15": 1, "30": 2, "40": 3, "ad": 4, "a": 4, "adv": 4}

# Higher priority = hotter alert.
CODE_PRIORITY = {
    "0-40": 6,
    "ad-break": 5,
    "15-40": 4,
    "30-40": 3,
    "break-point": 3,
    "tiebreak": 2,
    "deuce": 1,
}

# Human-readable label for Telegram messages (highest-priority alert wins).
CODE_LABEL = {
    "0-40": "0\u201340 \u00b7 triple break point",
    "15-40": "15\u201340 \u00b7 double break point",
    "30-40": "30\u201340 \u00b7 break point",
    "ad-break": "Advantage returner \u00b7 break point",
    "break-point": "Break point",
    "deuce": "Deuce",
    "tiebreak": "Tiebreak",
}


def _rank(point) -> int | None:
    return _POINT_RANK.get(str(point).strip().lower())


def compute_alerts(points_p1, points_p2, server, is_tiebreak):
    """Return ``(alerts, alert_label, alert_priority)`` for a game state.

    ``server`` is 1 or 2 (or 0/None if unknown). ``points_p1``/``points_p2`` are
    the displayed game points ("0", "15", "30", "40", "AD"). In a tiebreak the
    only alert is ``tiebreak`` (break points there are handled as set points and
    are out of scope).
    """
    alerts: list[str] = []

    if is_tiebreak:
        alerts.append("tiebreak")
        return _finalise(alerts)

    if server not in (1, 2):
        return _finalise(alerts)

    server_pts = points_p1 if server == 1 else points_p2
    returner_pts = points_p2 if server == 1 else points_p1

    s = _rank(server_pts)
    r = _rank(returner_pts)
    if s is None or r is None:
        return _finalise(alerts)

    # Deuce: 40-40, nobody ahead.
    if s == 3 and r == 3:
        alerts.append("deuce")
        return _finalise(alerts)

    # Returner holds advantage -> break point against the server.
    if r == 4 and s == 3:
        alerts.append("ad-break")
        alerts.append("break-point")
        return _finalise(alerts)

    # Returner on 40 with the server behind -> 0-40 / 15-40 / 30-40 break points.
    if r == 3 and s < 3:
        alerts.append({0: "0-40", 1: "15-40", 2: "30-40"}[s])
        alerts.append("break-point")

    return _finalise(alerts)


def _finalise(alerts):
    if not alerts:
        return [], None, 0
    priority = max(CODE_PRIORITY.get(a, 0) for a in alerts)
    # Label comes from the highest-priority alert code present.
    top = max(alerts, key=lambda a: CODE_PRIORITY.get(a, 0))
    return alerts, CODE_LABEL.get(top, top), priority
