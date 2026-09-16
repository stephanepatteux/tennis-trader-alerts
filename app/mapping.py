"""Map a Live Tennis API match/score frame into the normalised match shape.

Ported from live-tennis-scoreboard. Used for the Ultra WebSocket push frames.
Scores are PLAYER-MAJOR: ``sets=[p1,p2]``, ``games=[[p1 per set],[p2 per set]]``,
``points=[p1,p2]``, ``server`` is 1 or 2.
Reference: https://docs.livetennisapi.com (OpenAPI schema).
"""

from __future__ import annotations

from .matches import build_match


def _pair(seq, default=0):
    try:
        a = seq[0]
    except (IndexError, TypeError):
        a = default
    try:
        b = seq[1]
    except (IndexError, TypeError):
        b = default
    return a, b


def to_percent(value):
    """Normalise a win probability to a 0-100 percentage (accepts 0-1 or 0-100)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= v <= 1.0:
        v *= 100.0
    return round(v, 1)


def map_api_match(frame: dict, model_fallback: bool = True, static=None) -> dict:
    """Map one Match/score frame to a normalised match.

    ``static`` is an optional dict of previously-known static fields for this match
    (``p1``, ``p2``, ``tour``, ``tournament``, ``surface``, ``format``,
    ``is_doubles``), used when a score-only frame omits them.
    """
    static = static or {}
    players = frame.get("players") or {}
    p1 = (players.get("p1") or {}).get("name") or static.get("p1") or "Player 1"
    p2 = (players.get("p2") or {}).get("name") or static.get("p2") or "Player 2"

    score = frame.get("score") or {}
    sets = score.get("sets") or [0, 0]
    sets_p1, sets_p2 = _pair(sets)

    games = score.get("games")  # [[p1 per set], [p2 per set]] or null (withheld)
    games_p1_list = (games[0] if games and len(games) > 0 else []) or []
    games_p2_list = (games[1] if games and len(games) > 1 else []) or []
    games_p1 = games_p1_list[-1] if games_p1_list else 0
    games_p2 = games_p2_list[-1] if games_p2_list else 0
    set_history = " ".join(f"{a}-{b}" for a, b in zip(games_p1_list, games_p2_list))

    points = score.get("points") or ["0", "0"]
    points_p1, points_p2 = _pair(points, default="0")

    win_prob = to_percent(
        score.get("win_probability_p1_model")
        if score.get("win_probability_p1_model") is not None
        else score.get("win_probability_p1")
    )

    return build_match(
        id=frame.get("id") if frame.get("id") is not None else frame.get("match_id"),
        p1=p1,
        p2=p2,
        tour=frame.get("tour") or static.get("tour"),
        tournament=frame.get("tournament") or static.get("tournament"),
        surface=frame.get("surface") or static.get("surface"),
        fmt=frame.get("format") or static.get("format"),
        is_doubles=frame.get("is_doubles", static.get("is_doubles", False)),
        sets_p1=sets_p1,
        sets_p2=sets_p2,
        games_p1=games_p1,
        games_p2=games_p2,
        points_p1=points_p1,
        points_p2=points_p2,
        server=score.get("server") or 0,
        is_tiebreak=score.get("is_tiebreak", False),
        set_history=set_history,
        win_prob_p1=win_prob,
        model_fallback=model_fallback,
    )
