"""Tests for Telegram notifier formatting and sendMessage (mocked HTTP)."""

import io
import json
import urllib.error

import pytest

from app.matches import build_match
from app.notifier import TelegramNotifier, format_alert, html_escape


def _match(**kwargs):
    defaults = dict(
        id=9,
        p1="Iga Swiatek",
        p2="Aryna Sabalenka",
        tour="wta",
        tournament="Indian Wells",
        surface="hard",
        sets_p1=1,
        sets_p2=0,
        games_p1=3,
        games_p2=4,
        points_p1="40",
        points_p2="0",
        server=2,
        is_tiebreak=False,
        set_history="6-4 3-4",
        win_prob_p1=61.2,
        model_fallback=False,
    )
    defaults.update(kwargs)
    return build_match(**defaults)


def test_format_alert_includes_label_players_and_score():
    match = _match()
    text = format_alert(match, ["0-40"])
    assert "0–40" in text
    assert "triple break point" in text
    assert "Iga Swiatek" in text
    assert "Aryna Sabalenka" in text
    assert "WTA" in text
    assert "Indian Wells" in text
    assert "Hard" in text
    assert "40–0" in text
    assert "Serving: Aryna Sabalenka" in text
    assert "Model P1: 61.2%" in text
    assert "<b>" in text  # HTML parse_mode


def test_format_alert_escapes_html_in_player_names():
    match = _match(p1="A <script>", p2="B & C")
    text = format_alert(match, ["0-40"])
    assert "<script>" not in text
    assert "A &lt;script&gt;" in text
    assert "B &amp; C" in text


def test_html_escape():
    assert html_escape("a<b>c&d") == "a&lt;b&gt;c&amp;d"


def test_send_posts_sendMessage_with_chat_id_and_html(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True, "result": {"message_id": 7}}).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        captured["content_type"] = req.get_header("Content-type")
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = TelegramNotifier(token="TEST_TOKEN", api_base="https://api.telegram.test")
    match = _match()
    text = notifier.format_alert(match, ["0-40"])
    body = notifier.send("4242", text)

    assert body["ok"] is True
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.telegram.test/botTEST_TOKEN/sendMessage"
    assert captured["content_type"] == "application/json"
    assert captured["body"]["chat_id"] == "4242"
    assert captured["body"]["parse_mode"] == "HTML"
    assert captured["body"]["disable_web_page_preview"] is True
    assert "0–40" in captured["body"]["text"]
    assert "Iga Swiatek" in captured["body"]["text"]


def test_send_raises_when_telegram_returns_not_ok(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": False, "description": "Forbidden"}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())
    notifier = TelegramNotifier(token="TEST_TOKEN")
    with pytest.raises(RuntimeError, match="Forbidden"):
        notifier.send("1", "hello")


def test_http_error_does_not_leak_bot_token(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"ok":false,"description":"Unauthorized"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", boom)
    notifier = TelegramNotifier(token="SUPER_SECRET_TOKEN")
    with pytest.raises(RuntimeError, match="HTTP 401") as caught:
        notifier.send("1", "hello")
    assert "SUPER_SECRET_TOKEN" not in str(caught.value)
    assert "SUPER_SECRET_TOKEN" not in repr(caught.value)
