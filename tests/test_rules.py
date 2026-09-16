"""Tests for the per-user rules store and match filters."""

import json
from pathlib import Path

from app.matches import build_match
from app.rules import DEFAULT_TRIGGERS, RulesStore, UserRule


def _match(**kwargs):
    defaults = dict(
        id=1,
        p1="Jannik Sinner",
        p2="Carlos Alcaraz",
        tour="atp",
        surface="clay",
        points_p1="40",
        points_p2="15",
        server=2,
        model_fallback=False,
    )
    defaults.update(kwargs)
    return build_match(**defaults)


def test_tour_filter():
    user = UserRule(chat_id="1", tours=["wta"])
    assert user.matches_filters(_match(tour="atp")) is False
    assert user.matches_filters(_match(tour="wta", p1="Iga", p2="Aryna")) is True


def test_surface_filter():
    user = UserRule(chat_id="1", surfaces=["hard", "grass"])
    assert user.matches_filters(_match(surface="clay")) is False
    assert user.matches_filters(_match(surface="hard")) is True


def test_empty_filters_match_everything():
    user = UserRule(chat_id="1", tours=[], surfaces=[], watchlist=[])
    assert user.matches_filters(_match()) is True


def test_watchlist_substring_case_insensitive():
    user = UserRule(chat_id="1", watchlist=["sinner"])
    assert user.matches_filters(_match()) is True
    assert user.matches_filters(_match(p1="Iga", p2="Aryna")) is False


def test_any_bp_rising_from_idle():
    user = UserRule(chat_id="1", triggers=["break-point"])
    hits = user.matching_triggers(frozenset(), frozenset({"0-40", "break-point"}))
    assert hits == ["break-point"]


def test_any_bp_stays_quiet_while_still_in_breakpoint():
    user = UserRule(chat_id="1", triggers=["break-point"])
    prev = frozenset({"0-40", "break-point"})
    current = frozenset({"15-40", "break-point"})
    assert user.matching_triggers(prev, current) == []


def test_deuce_then_ad_break_is_any_bp_rising():
    user = UserRule(chat_id="1", triggers=["break-point", "deuce"])
    deuce = user.matching_triggers(frozenset(), frozenset({"deuce"}))
    assert deuce == ["deuce"]
    ad = user.matching_triggers(
        frozenset({"deuce"}), frozenset({"ad-break", "break-point"})
    )
    assert ad == ["break-point"]


def test_rules_store_from_file(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "chat_id": 111,
                        "name": "trader",
                        "triggers": ["0-40", "15-40"],
                        "tours": ["ATP"],
                        "surfaces": ["Clay"],
                        "watchlist": ["Sinner"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = RulesStore.load(path)
    users = store.users()
    assert len(users) == 1
    u = users[0]
    assert u.chat_id == "111"
    assert u.triggers == ["0-40", "15-40"]
    assert u.tours == ["atp"]
    assert u.surfaces == ["clay"]
    assert u.watchlist == ["Sinner"]


def test_rules_store_env_bootstrap(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("RULES_PATH", str(missing))
    empty = RulesStore.load(missing)
    assert empty.users() == []
    assert empty.path == missing

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("ALERT_TRIGGERS", "deuce,tiebreak")
    monkeypatch.setenv("ALERT_TOURS", "wta")
    store = RulesStore.load(missing)
    u = store.users()[0]
    assert u.chat_id == "999"
    assert u.triggers == ["deuce", "tiebreak"]
    assert u.tours == ["wta"]


def test_maybe_reload_picks_up_file_change(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"users": [{"chat_id": "1", "triggers": ["deuce"]}]}), encoding="utf-8")
    store = RulesStore.load(path)
    assert store.users()[0].triggers == ["deuce"]
    path.write_text(
        json.dumps({"users": [{"chat_id": "1", "triggers": ["0-40"]}]}),
        encoding="utf-8",
    )
    # Force mtime into the future so the change is visible even on coarse FS clocks.
    import os
    import time

    os.utime(path, (time.time() + 5, time.time() + 5))
    assert store.maybe_reload() is True
    assert store.users()[0].triggers == ["0-40"]


def test_omitted_triggers_default_to_all(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"users": [{"chat_id": "1"}]}), encoding="utf-8")
    assert RulesStore.load(path).users()[0].triggers == list(DEFAULT_TRIGGERS)


def test_empty_triggers_mean_none(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps({"users": [{"chat_id": "1", "triggers": []}]}), encoding="utf-8"
    )
    user = RulesStore.load(path).users()[0]
    assert user.triggers == []
    assert user.matching_triggers(frozenset(), frozenset({"deuce"})) == []
