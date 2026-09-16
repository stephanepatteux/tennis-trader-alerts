"""Tests for the Telegram bot settings menu."""

from pathlib import Path

from app.bot import MAX_WATCHLIST, BotMenu, format_status, menu_keyboard
from app.rules import RulesStore, UserRule, toggle_subset


class FakeApi:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.answered = []
        self.commands = None

    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None):
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )
        return {"ok": True, "result": {"message_id": len(self.sent)}}

    def edit_message_text(self, chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return {"ok": True}

    def answer_callback_query(self, callback_query_id, text=""):
        self.answered.append({"id": callback_query_id, "text": text})
        return {"ok": True}

    def get_updates(self, offset=0, timeout=30):
        return []

    def set_my_commands(self, commands):
        self.commands = commands
        return {"ok": True}


def _store(tmp_path: Path) -> RulesStore:
    return RulesStore([], path=tmp_path / "rules.json")


def _bot(tmp_path: Path, allowed=None):
    api = FakeApi()
    store = _store(tmp_path)
    return BotMenu(api, store, allowed_chats=allowed), api, store


def _msg(chat_id, text, username="alice"):
    return {
        "message": {
            "chat": {"id": chat_id},
            "text": text,
            "from": {"username": username, "first_name": "Alice"},
        }
    }


def _cb(chat_id, data, message_id=1, qid="q1"):
    return {
        "callback_query": {
            "id": qid,
            "data": data,
            "from": {"username": "alice"},
            "message": {"message_id": message_id, "chat": {"id": chat_id}},
        }
    }


def test_start_enrolls_user_and_opens_menu(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(42, "/start"))
    assert store.get("42") is not None
    assert store.get("42").enabled is True
    assert any("Tennis Trader Alerts" in m["text"] for m in api.sent)
    assert any((m.get("reply_markup") or {}).get("inline_keyboard") for m in api.sent)
    saved = (tmp_path / "rules.json").read_text(encoding="utf-8")
    assert '"chat_id": "42"' in saved


def test_start_at_botname_works(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(7, "/start@TennisTraderAlertsBot"))
    assert store.get("7") is not None


def test_toggle_trigger_from_callback_persists(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "/start"))
    assert "deuce" in store.get("1").triggers
    bot.handle_update(_cb(1, "tg:deuce", message_id=2))
    assert "deuce" not in store.get("1").triggers
    assert api.answered and api.edited
    bot.handle_update(_cb(1, "tg:deuce", message_id=2, qid="q2"))
    assert "deuce" in store.get("1").triggers


def test_pause_and_resume_from_menu(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "/start"))
    bot.handle_update(_cb(1, "en"))
    assert store.get("1").enabled is False
    bot.handle_update(_msg(1, "Pause"))
    assert store.get("1").enabled is False
    bot.handle_update(_msg(1, "/on"))
    assert store.get("1").enabled is True


def test_tour_and_surface_filters(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "/start"))
    bot.handle_update(_cb(1, "tr:atp"))
    assert store.get("1").tours == ["wta"]
    bot.handle_update(_cb(1, "sf:clay"))
    bot.handle_update(_cb(1, "sf:grass"))
    assert store.get("1").surfaces == ["hard"]


def test_watchlist_add_and_remove(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "/start"))
    bot.handle_update(_cb(1, "wl+"))
    bot.handle_update(_msg(1, "Sinner"))
    assert store.get("1").watchlist == ["Sinner"]
    bot.handle_update(_cb(1, "wlx:0"))
    assert store.get("1").watchlist == []


def test_watchlist_cancel(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "/start"))
    bot.handle_update(_cb(1, "wl+"))
    bot.handle_update(_msg(1, "/cancel"))
    assert store.get("1").watchlist == []


def test_allowed_chats_rejects_others(tmp_path: Path):
    bot, api, store = _bot(tmp_path, allowed=["99"])
    bot.handle_update(_msg(1, "/start"))
    assert store.get("1") is None
    assert "private" in api.sent[-1]["text"].lower()


def test_reply_keyboard_menu_button(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    bot.handle_update(_msg(1, "⚙️ Menu"))
    assert store.get("1") is not None
    assert any("Alert settings" in m["text"] for m in api.sent)


def test_menu_keyboard_has_trigger_and_filter_buttons():
    user = UserRule(chat_id="1")
    kb = menu_keyboard(user)
    labels = [btn["text"] for row in kb["inline_keyboard"] for btn in row]
    joined = " ".join(labels)
    assert "0–40" in joined and "Any BP" in joined
    assert "ATP" in joined and "Clay" in joined
    assert "➕ Player" in joined
    status = format_status(user)
    assert "ON" in status


def test_toggle_subset_empty_means_all():
    assert toggle_subset([], "atp", ("atp", "wta")) == ["wta"]
    assert toggle_subset(["wta"], "atp", ("atp", "wta")) == []
    assert toggle_subset(["hard"], "clay", ("clay", "hard", "grass")) == ["clay", "hard"]


def test_existing_user_bypasses_allowlist(tmp_path: Path):
    bot, api, store = _bot(tmp_path, allowed=["99"])
    store.get_or_create("1")
    bot.handle_update(_msg(1, "/menu"))
    assert any("Alert settings" in m["text"] for m in api.sent)


def test_callback_falls_back_to_from_id(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    store.get_or_create("5")
    bot.handle_update(
        {
            "callback_query": {
                "id": "q",
                "data": "tg:deuce",
                "from": {"id": 5, "username": "alice"},
                "message": {"message_id": 9},
            }
        }
    )
    assert "deuce" not in store.get("5").triggers


def test_watchlist_rejects_when_full(tmp_path: Path):
    bot, api, store = _bot(tmp_path)
    user = store.get_or_create("1")
    user.watchlist = [f"P{i}" for i in range(MAX_WATCHLIST)]
    store.save()
    bot.handle_update(_cb(1, "wl+"))
    bot.handle_update(_msg(1, "Extra"))
    assert "Extra" not in store.get("1").watchlist
    assert any("full" in m["text"].lower() for m in api.sent)
