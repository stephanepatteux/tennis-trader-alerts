"""Tests for break-point / score alert detection."""

from app.scoring.alerts import compute_alerts


def test_no_alert_when_server_ahead():
    # Server (p1) leads 40-30 — a hold point, not a trading signal.
    alerts, label, prio = compute_alerts("40", "30", server=1, is_tiebreak=False)
    assert alerts == []
    assert prio == 0
    assert label is None


def test_zero_forty_triple_break_point():
    # p2 serving, p1 returning at 40 with server on 0 -> 0-40 against p2.
    alerts, label, prio = compute_alerts("40", "0", server=2, is_tiebreak=False)
    assert "0-40" in alerts
    assert "break-point" in alerts
    assert prio == 6
    assert "0" in label


def test_fifteen_forty():
    alerts, label, prio = compute_alerts("40", "15", server=2, is_tiebreak=False)
    assert "15-40" in alerts and "break-point" in alerts
    assert prio == 4


def test_thirty_forty():
    alerts, _, prio = compute_alerts("40", "30", server=2, is_tiebreak=False)
    assert "30-40" in alerts and "break-point" in alerts
    assert prio == 3


def test_deuce():
    alerts, label, prio = compute_alerts("40", "40", server=1, is_tiebreak=False)
    assert alerts == ["deuce"]
    assert label == "Deuce"
    assert prio == 1


def test_advantage_returner_is_break_point():
    # Server p1; returner p2 has advantage -> break point against p1.
    alerts, label, prio = compute_alerts("40", "AD", server=1, is_tiebreak=False)
    assert "ad-break" in alerts and "break-point" in alerts
    assert prio == 5


def test_advantage_server_is_not_alert():
    # Server p1 holds advantage -> no alert (server is not under threat).
    alerts, _, prio = compute_alerts("AD", "40", server=1, is_tiebreak=False)
    assert alerts == []
    assert prio == 0


def test_tiebreak():
    alerts, label, prio = compute_alerts("5", "6", server=1, is_tiebreak=True)
    assert alerts == ["tiebreak"]
    assert label == "Tiebreak"


def test_unknown_server_no_break_point():
    alerts, _, prio = compute_alerts("40", "0", server=0, is_tiebreak=False)
    assert alerts == []
