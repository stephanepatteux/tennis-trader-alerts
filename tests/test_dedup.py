"""Tests for rising-edge de-dup, rate limiting, and dispatch."""

from app.dispatch import Dispatcher, RateLimiter, RisingEdgeDeduper
from app.matches import build_match
from app.rules import RulesStore, UserRule


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def format_alert(self, match, triggers):
        return f"{match['p1']} vs {match['p2']} :: {','.join(triggers)}"

    def send(self, chat_id, text, parse_mode="HTML"):
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {"ok": True}


def _match(**kwargs):
    defaults = dict(
        id=1,
        p1="Alice",
        p2="Bob",
        tour="atp",
        tournament="Test Open",
        surface="hard",
        points_p1="0",
        points_p2="0",
        server=1,
        is_tiebreak=False,
        model_fallback=False,
    )
    defaults.update(kwargs)
    return build_match(**defaults)


def _dispatcher(users, max_events=20, window_s=60.0, clock=None):
    limiter = RateLimiter(
        max_events=max_events,
        window_s=window_s,
        time_fn=clock or (lambda: 0.0),
    )
    notifier = RecordingNotifier()
    disp = Dispatcher(RulesStore(users), notifier, rate_limiter=limiter)
    return disp, notifier


def test_rising_edge_fires_once_while_score_holds():
    deduper = RisingEdgeDeduper()
    first_prev, first_cur = deduper.update(1, ["0-40", "break-point"])
    assert first_prev == frozenset()
    assert "0-40" in first_cur
    second_prev, second_cur = deduper.update(1, ["0-40", "break-point"])
    assert second_prev == second_cur


def test_rising_edge_refires_after_alert_clears():
    deduper = RisingEdgeDeduper()
    deduper.update(1, ["0-40", "break-point"])
    deduper.update(1, [])  # point played, alert gone
    prev, current = deduper.update(1, ["0-40", "break-point"])
    assert "0-40" in current and "0-40" not in prev


def test_dispatcher_dedups_same_breakpoint():
    user = UserRule(chat_id="100", triggers=["0-40", "break-point"])
    disp, notifier = _dispatcher([user])
    bp = _match(points_p1="40", points_p2="0", server=2)
    assert "0-40" in bp["alerts"]

    first = disp.handle(bp)
    assert [r["status"] for r in first] == ["sent"]
    second = disp.handle(bp)
    assert second == []
    assert len(notifier.sent) == 1


def test_dispatcher_refires_when_breakpoint_returns():
    user = UserRule(chat_id="100", triggers=["0-40"])
    disp, notifier = _dispatcher([user])
    bp = _match(points_p1="40", points_p2="0", server=2)
    idle = _match(points_p1="0", points_p2="0", server=2)
    disp.handle(bp)
    disp.handle(idle)
    again = disp.handle(bp)
    assert [r["status"] for r in again] == ["sent"]
    assert len(notifier.sent) == 2


def test_any_bp_does_not_refire_when_score_moves_0_40_to_15_40():
    user = UserRule(chat_id="100", triggers=["break-point"])
    disp, notifier = _dispatcher([user])
    triple = _match(points_p1="40", points_p2="0", server=2)
    double = _match(points_p1="40", points_p2="15", server=2)
    disp.handle(triple)
    moved = disp.handle(double)
    assert moved == []
    assert len(notifier.sent) == 1


def test_specific_15_40_fires_when_moving_from_0_40():
    user = UserRule(chat_id="100", triggers=["15-40"])
    disp, notifier = _dispatcher([user])
    disp.handle(_match(points_p1="40", points_p2="0", server=2))
    results = disp.handle(_match(points_p1="40", points_p2="15", server=2))
    assert [r["status"] for r in results] == ["sent"]
    assert results[0]["triggers"] == ["15-40"]


def test_rate_limiter_blocks_after_max_events():
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    limiter = RateLimiter(max_events=2, window_s=60.0, time_fn=now)
    assert limiter.allow("u1")
    assert limiter.allow("u1")
    assert limiter.allow("u1") is False
    assert limiter.allow("u2")  # other user is independent
    clock["t"] = 61.0
    assert limiter.allow("u1")


def test_dispatcher_rate_limits_per_user():
    user = UserRule(chat_id="100", triggers=["0-40", "deuce"])
    disp, notifier = _dispatcher([user], max_events=1, window_s=60.0)
    first = disp.handle(_match(id=1, points_p1="40", points_p2="0", server=2))
    second = disp.handle(_match(id=2, points_p1="40", points_p2="40", server=1))
    assert first[0]["status"] == "sent"
    assert second[0]["status"] == "rate_limited"
    assert len(notifier.sent) == 1
