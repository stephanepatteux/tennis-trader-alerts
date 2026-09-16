"""Tests for the Ultra push source (frame handling, token minting)."""

import json
import os
from unittest import mock

import pytest

from app.config import ConfigError
from app.push import PushHub, UltraPushSource, get_push_source


def test_get_push_source_requires_ultra_key():
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError, match="LIVE_TENNIS_API_KEY"):
            get_push_source()
    with mock.patch.dict(os.environ, {"LIVE_TENNIS_API_KEY": "test-key"}, clear=True):
        src = get_push_source()
        assert isinstance(src, UltraPushSource)
        assert src.api_key == "test-key"


def test_ultra_handle_raw_publishes_score_frame():
    hub = PushHub(source_name="livetennisapi-ultra")
    src = UltraPushSource(api_key="k", base_url="http://api.test/v1")
    frame = {
        "push": {
            "channel": "slate:all",
            "pub": {
                "data": {
                    "id": 100,
                    "tour": "wta",
                    "players": {"p1": {"name": "Iga"}, "p2": {"name": "Aryna"}},
                    "score": {
                        "sets": [0, 0],
                        "games": [[2], [1]],
                        "points": ["40", "0"],
                        "server": 2,
                    },
                }
            },
        }
    }
    src.handle_raw(json.dumps(frame), hub)
    matches = hub.snapshot()["matches"]
    assert len(matches) == 1
    m = matches[0]
    assert m["id"] == 100 and m["p1"] == "Iga"
    assert "0-40" in m["alerts"]  # p1 at 40 on p2's serve, server on 0


def test_ultra_handle_raw_replies_to_heartbeat():
    hub = PushHub()
    src = UltraPushSource(api_key="k", base_url="http://api.test/v1")
    sent = []

    class FakeWs:
        def send(self, msg):
            sent.append(msg)

    src.handle_raw("{}", hub, ws=FakeWs())
    assert sent == ["{}"]
    assert hub.snapshot()["matches"] == []  # heartbeat is not a score


def test_ultra_handle_raw_ignores_connect_replies():
    hub = PushHub()
    src = UltraPushSource(api_key="k", base_url="http://api.test/v1")
    src.handle_raw(json.dumps({"id": 1, "connect": {"client": "abc"}}), hub)
    assert hub.snapshot()["matches"] == []


def test_ultra_handle_raw_batched_newline_delimited():
    hub = PushHub()
    src = UltraPushSource(api_key="k", base_url="http://api.test/v1")
    f1 = {
        "push": {
            "pub": {
                "data": {
                    "id": 1,
                    "players": {"p1": {"name": "A"}, "p2": {"name": "B"}},
                    "score": {"sets": [0, 0], "points": ["0", "0"], "server": 1},
                }
            }
        }
    }
    f2 = {
        "push": {
            "pub": {
                "data": {
                    "id": 2,
                    "players": {"p1": {"name": "C"}, "p2": {"name": "D"}},
                    "score": {"sets": [0, 0], "points": ["0", "0"], "server": 1},
                }
            }
        }
    }
    src.handle_raw(json.dumps(f1) + "\n" + json.dumps(f2), hub)
    assert len(hub.snapshot()["matches"]) == 2


def test_ultra_mint_ws_token_uses_bearer_auth():
    src = UltraPushSource(api_key="test-key", base_url="http://api.test/v1")
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"token": "tok", "ws_url": "wss://x/ws", "channels": {"slate": "slate:all"}}
            ).encode()

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")
        captured["url"] = req.full_url
        return FakeResp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        info = src.mint_ws_token()
    assert info["ws_url"] == "wss://x/ws"
    assert captured["auth"] == "Bearer test-key"
    assert captured["url"].endswith("/ws-token")
