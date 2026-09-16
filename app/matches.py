"""The normalised match shape every source produces.

Ported from live-tennis-scoreboard so mapping + alert detection stay in lockstep
with the trader board.
"""

from __future__ import annotations

from .scoring import compute_alerts, estimate_win_prob_p1


def normalise_tour(tour) -> str:
    t = (str(tour or "")).strip().lower()
    if t in ("men", "atp"):
        return "atp"
    if t in ("women", "wta"):
        return "wta"
    return t or "unknown"


def build_match(
    *,
    id,
    p1,
    p2,
    tour=None,
    tournament=None,
    surface=None,
    fmt=None,
    is_doubles=False,
    sets_p1=0,
    sets_p2=0,
    games_p1=0,
    games_p2=0,
    points_p1="0",
    points_p2="0",
    server=0,
    is_tiebreak=False,
    set_history="",
    win_prob_p1=None,
    model_fallback=True,
) -> dict:
    """Assemble one normalised match, computing alerts and (optionally) the model."""
    alerts, alert_label, alert_priority = compute_alerts(
        points_p1, points_p2, server, is_tiebreak
    )

    if win_prob_p1 is None and model_fallback:
        win_prob_p1 = estimate_win_prob_p1(
            sets_p1,
            sets_p2,
            games_p1,
            games_p2,
            points_p1,
            points_p2,
            server,
            is_tiebreak,
        )

    return {
        "id": id,
        "tour": normalise_tour(tour),
        "p1": p1,
        "p2": p2,
        "tournament": tournament,
        "surface": (surface or "").lower() or None,
        "format": fmt,
        "is_doubles": bool(is_doubles),
        "sets_p1": sets_p1,
        "sets_p2": sets_p2,
        "games_p1": games_p1,
        "games_p2": games_p2,
        "points_p1": points_p1,
        "points_p2": points_p2,
        "server": server if server in (1, 2) else 0,
        "is_tiebreak": bool(is_tiebreak),
        "set_history": set_history,
        "alerts": alerts,
        "alert_label": alert_label,
        "alert_priority": alert_priority,
        "win_prob_p1": win_prob_p1,
    }
