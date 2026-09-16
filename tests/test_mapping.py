"""Tests for mapping Live Tennis API frames into the normalised match shape."""

from app.mapping import map_api_match, to_percent


def test_maps_full_match_frame():
    frame = {
        "id": 42,
        "tournament": "Test Open",
        "tour": "ATP",
        "surface": "Hard",
        "format": "Bo3",
        "is_doubles": False,
        "players": {"p1": {"name": "Alice"}, "p2": {"name": "Bob"}},
        "score": {
            "sets": [1, 0],
            "games": [[6, 3], [4, 4]],
            "points": ["40", "15"],
            "server": 2,
            "is_tiebreak": False,
            "win_probability_p1": 0.72,
        },
    }
    m = map_api_match(frame)
    assert m["id"] == 42
    assert m["tour"] == "atp" and m["surface"] == "hard"
    assert m["p1"] == "Alice" and m["p2"] == "Bob"
    assert m["sets_p1"] == 1 and m["sets_p2"] == 0
    assert m["games_p1"] == 3 and m["games_p2"] == 4  # last per-set entry
    assert m["set_history"] == "6-4 3-4"
    assert m["points_p1"] == "40" and m["points_p2"] == "15"
    assert "break-point" in m["alerts"]  # p1 returning on p2 serve at 40-15
    assert m["win_prob_p1"] == 72.0  # provider model normalised to %


def test_prefers_ultra_model_field():
    frame = {
        "id": 1,
        "players": {"p1": {"name": "A"}, "p2": {"name": "B"}},
        "score": {
            "sets": [0, 0],
            "points": ["0", "0"],
            "server": 1,
            "win_probability_p1": 0.4,
            "win_probability_p1_model": 0.65,
        },
    }
    assert map_api_match(frame)["win_prob_p1"] == 65.0


def test_score_only_frame_uses_static_lookup():
    frame = {"match_id": 7, "score": {"sets": [0, 0], "points": ["30", "40"], "server": 1}}
    static = {"p1": "Carla", "p2": "Dana", "tour": "wta", "tournament": "X"}
    m = map_api_match(frame, static=static)
    assert m["id"] == 7
    assert m["p1"] == "Carla" and m["p2"] == "Dana" and m["tour"] == "wta"
    # p2 returning at 40 vs server 30 -> break point against server p1.
    assert "30-40" in m["alerts"] and "break-point" in m["alerts"]


def test_withheld_games_and_null_handled():
    frame = {
        "id": 5,
        "players": {"p1": {"name": "A"}, "p2": {"name": "B"}},
        "score": {"sets": [0, 0], "games": None, "points": ["0", "0"], "server": 1},
    }
    m = map_api_match(frame)
    assert m["games_p1"] == 0 and m["set_history"] == ""


def test_to_percent():
    assert to_percent(0.5) == 50.0
    assert to_percent(73) == 73.0
    assert to_percent(None) is None
    assert to_percent("bad") is None
