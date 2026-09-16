"""Telegram bot menu so each chat can manage its own alert rules.

Long-polls ``getUpdates``. Inline buttons toggle triggers and filters; a
persistent reply keyboard exposes Menu / Status / Pause / Resume. Settings are
written to the same ``data/rules.json`` store the worker uses.
"""

from __future__ import annotations

import logging
import threading

from .notifier import html_escape
from .rules import SURFACES, TOURS, VALID_TRIGGERS, RulesStore, UserRule, toggle_subset

log = logging.getLogger(__name__)

BOT_COMMANDS = [
    {"command": "start", "description": "Start and open the alert menu"},
    {"command": "menu", "description": "Manage alert triggers and filters"},
    {"command": "status", "description": "Show your current alert settings"},
    {"command": "on", "description": "Enable alerts"},
    {"command": "off", "description": "Pause alerts"},
    {"command": "help", "description": "How alerts and filters work"},
]

TRIGGER_BUTTONS = (
    ("0-40", "0–40"),
    ("15-40", "15–40"),
    ("30-40", "30–40"),
    ("break-point", "Any BP"),
    ("deuce", "Deuce"),
    ("tiebreak", "Tiebreak"),
)

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "⚙️ Menu"}, {"text": "Status"}],
        [{"text": "Pause"}, {"text": "Resume"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

HELP_TEXT = (
    "<b>Tennis Trader Alerts</b>\n"
    "You'll get a Telegram message the instant a live match hits a trigger "
    "you turned on.\n\n"
    "<b>Triggers</b> (tap in /menu):\n"
    "• <b>0–40</b> triple break point\n"
    "• <b>15–40</b> double break point\n"
    "• <b>30–40</b> break point\n"
    "• <b>Any BP</b> first moment the returner has a break point\n"
    "• <b>Deuce</b> and <b>Tiebreak</b>\n\n"
    "<b>Filters</b> — leave a row all-on to receive every tour / surface. "
    "A player watchlist, if set, limits alerts to those names.\n\n"
    "Use /menu to change this. /off pauses without wiping your filters."
)

WELCOME_TEXT = (
    "🎾 <b>Tennis Trader Alerts</b>\n"
    "Instant Telegram pings on live break-point situations.\n\n"
    "Open the menu to choose which triggers fire and which matches to watch."
)


def _tick(on: bool, label: str) -> str:
    return f"{'✅' if on else '☐'} {label}"


def _filter_on(selected: list[str], value: str) -> bool:
    return (not selected) or value in selected


def format_status(user: UserRule) -> str:
    state = "ON" if user.enabled else "PAUSED"
    trigger_bits = []
    for code, label in TRIGGER_BUTTONS:
        mark = "✅" if code in user.triggers else "☐"
        trigger_bits.append(f"{mark} {label}")
    tours = ", ".join(t.upper() for t in user.tours) if user.tours else "All"
    surfaces = ", ".join(s.title() for s in user.surfaces) if user.surfaces else "All"
    watch = ", ".join(user.watchlist) if user.watchlist else "All players"
    return (
        f"🎾 <b>Alert settings</b> — {html_escape(state)}\n\n"
        f"<b>Triggers</b>\n" + " · ".join(trigger_bits) + "\n\n"
        f"<b>Tour</b>: {html_escape(tours)}\n"
        f"<b>Surface</b>: {html_escape(surfaces)}\n"
        f"<b>Watchlist</b>: {html_escape(watch)}\n\n"
        "Tap the buttons to change. Empty tour/surface/watchlist = all matches."
    )


def menu_keyboard(user: UserRule) -> dict:
    rows: list[list[dict]] = []
    pause_label = "⏸ Pause alerts" if user.enabled else "▶️ Resume alerts"
    rows.append([{"text": pause_label, "callback_data": "en"}])

    row: list[dict] = []
    for i, (code, label) in enumerate(TRIGGER_BUTTONS):
        row.append(
            {
                "text": _tick(code in user.triggers, label),
                "callback_data": f"tg:{code}",
            }
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(
        [
            {"text": _tick(_filter_on(user.tours, "atp"), "ATP"), "callback_data": "tr:atp"},
            {"text": _tick(_filter_on(user.tours, "wta"), "WTA"), "callback_data": "tr:wta"},
        ]
    )
    rows.append(
        [
            {
                "text": _tick(_filter_on(user.surfaces, s), s.title()),
                "callback_data": f"sf:{s}",
            }
            for s in SURFACES
        ]
    )

    watch_row = [{"text": "➕ Player", "callback_data": "wl+"}]
    if user.watchlist:
        watch_row.append({"text": "Clear watchlist", "callback_data": "wl-"})
    rows.append(watch_row)
    for i, name in enumerate(user.watchlist):
        shown = name if len(name) <= 24 else name[:23] + "…"
        rows.append([{"text": f"✕ {shown}", "callback_data": f"wlx:{i}"}])
    return {"inline_keyboard": rows}


class BotMenu:
    def __init__(self, api, rules: RulesStore, allowed_chats=None):
        self.api = api
        self.rules = rules
        self.allowed = {str(c).strip() for c in (allowed_chats or []) if str(c).strip()}
        self._pending: dict[str, str] = {}
        self._stop = threading.Event()
        self._thread = None
        self._offset = 0

    def start(self) -> None:
        try:
            self.api.set_my_commands(BOT_COMMANDS)
        except Exception:
            log.exception("setMyCommands failed")
        self._thread = threading.Thread(target=self._poll, name="telegram-bot", daemon=True)
        self._thread.start()
        log.info("Telegram bot menu started")

    def stop(self) -> None:
        self._stop.set()

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                updates = self.api.get_updates(offset=self._offset, timeout=30)
            except Exception:
                if self._stop.is_set():
                    return
                log.exception("getUpdates failed")
                self._stop.wait(3.0)
                continue
            for update in updates:
                uid = update.get("update_id")
                if isinstance(uid, int):
                    self._offset = uid + 1
                try:
                    self.handle_update(update)
                except Exception:
                    log.exception("Failed to handle Telegram update")

    def allowed_chat(self, chat_id) -> bool:
        if not self.allowed:
            return True
        return str(chat_id).strip() in self.allowed

    def handle_update(self, update: dict) -> None:
        if update.get("callback_query"):
            self._on_callback(update["callback_query"])
            return
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat = (message.get("chat") or {}).get("id")
        if chat is None:
            return
        if not self.allowed_chat(chat):
            self.api.send_message(
                chat,
                "This bot is private. Ask the operator to add your chat id.",
                parse_mode="HTML",
            )
            return
        text = (message.get("text") or "").strip()
        from_user = message.get("from") or {}
        name = from_user.get("username") or from_user.get("first_name") or ""
        self._on_text(chat, text, name=name)

    def _on_text(self, chat_id, text: str, name: str = "") -> None:
        key = str(chat_id)
        pending = self._pending.get(key)
        cmd = _command_key(text)
        if pending == "watchlist_add" and not _is_command(text):
            self._add_player(chat_id, text)
            return
        if pending and cmd in ("cancel",):
            self._pending.pop(key, None)
            self.api.send_message(chat_id, "Cancelled.", reply_markup=REPLY_KEYBOARD)
            return

        if _is_command(text):
            self._pending.pop(key, None)

        if cmd in ("start",):
            self.rules.get_or_create(chat_id, name=name)
            self.api.send_message(chat_id, WELCOME_TEXT, reply_markup=REPLY_KEYBOARD)
            self._send_menu(chat_id)
            return
        if cmd in ("menu", "⚙️ menu", "⚙ menu", "settings"):
            self._send_menu(chat_id, name=name)
            return
        if cmd in ("status",):
            user = self.rules.get_or_create(chat_id, name=name)
            self.api.send_message(chat_id, format_status(user), reply_markup=REPLY_KEYBOARD)
            return
        if cmd in ("help",):
            self.api.send_message(chat_id, HELP_TEXT, reply_markup=REPLY_KEYBOARD)
            return
        if cmd in ("on", "resume", "play"):
            self._set_enabled(chat_id, True)
            return
        if cmd in ("off", "pause", "stop"):
            self._set_enabled(chat_id, False)
            return
        self.api.send_message(
            chat_id,
            "Use /menu to manage alerts, or tap ⚙️ Menu.",
            reply_markup=REPLY_KEYBOARD,
        )

    def _on_callback(self, query: dict) -> None:
        data = str(query.get("data") or "")
        qid = query.get("id")
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        from_user = query.get("from") or {}
        if chat_id is None:
            if qid:
                self.api.answer_callback_query(qid)
            return
        if not self.allowed_chat(chat_id):
            if qid:
                self.api.answer_callback_query(qid, text="Not allowed")
            return
        name = from_user.get("username") or from_user.get("first_name") or ""
        toast = self._apply_callback(chat_id, data, name=name)
        if qid:
            try:
                self.api.answer_callback_query(qid, text=toast)
            except Exception:
                log.exception("answerCallbackQuery failed")
        if data == "wl+":
            return
        if message_id is not None:
            user = self.rules.get_or_create(chat_id, name=name)
            try:
                self.api.edit_message_text(
                    chat_id,
                    message_id,
                    format_status(user),
                    reply_markup=menu_keyboard(user),
                )
            except Exception:
                log.exception("editMessageText failed")

    def _apply_callback(self, chat_id, data: str, name: str = "") -> str:
        if data == "en":
            user = self.rules.mutate(chat_id, lambda u: setattr(u, "enabled", not u.enabled))
            return "Alerts on" if user.enabled else "Alerts paused"
        if data.startswith("tg:"):
            code = data[3:]
            if code not in VALID_TRIGGERS:
                return ""
            self.rules.mutate(chat_id, lambda u, c=code: u.toggle_trigger(c))
            return ""
        if data.startswith("tr:"):
            value = data[3:]
            if value not in TOURS:
                return ""
            self.rules.mutate(
                chat_id, lambda u, v=value: setattr(u, "tours", toggle_subset(u.tours, v, TOURS))
            )
            return ""
        if data.startswith("sf:"):
            value = data[3:]
            if value not in SURFACES:
                return ""
            self.rules.mutate(
                chat_id,
                lambda u, v=value: setattr(u, "surfaces", toggle_subset(u.surfaces, v, SURFACES)),
            )
            return ""
        if data == "wl+":
            self._pending[str(chat_id)] = "watchlist_add"
            self.api.send_message(
                chat_id,
                "Send a player name to add to your watchlist, or /cancel.",
                reply_markup=REPLY_KEYBOARD,
            )
            return "Send a player name"
        if data == "wl-":
            self.rules.mutate(chat_id, lambda u: setattr(u, "watchlist", []))
            return "Watchlist cleared"
        if data.startswith("wlx:"):
            try:
                idx = int(data.split(":", 1)[1])
            except ValueError:
                return ""

            def _remove(user, i=idx):
                if 0 <= i < len(user.watchlist):
                    user.watchlist.pop(i)

            self.rules.mutate(chat_id, _remove)
            return "Removed"
        self.rules.get_or_create(chat_id, name=name)
        return ""

    def _add_player(self, chat_id, raw: str) -> None:
        name = (raw or "").strip()
        self._pending.pop(str(chat_id), None)
        if not name or name.startswith("/"):
            self.api.send_message(chat_id, "No player added.", reply_markup=REPLY_KEYBOARD)
            return

        def _add(user, n=name):
            existing = {w.lower() for w in user.watchlist}
            if n.lower() not in existing:
                user.watchlist.append(n)

        user = self.rules.mutate(chat_id, _add)
        self.api.send_message(
            chat_id,
            f"Watching <b>{html_escape(name)}</b>.",
            reply_markup=REPLY_KEYBOARD,
        )
        self._send_menu(chat_id, user=user)

    def _set_enabled(self, chat_id, enabled: bool) -> None:
        user = self.rules.mutate(chat_id, lambda u, e=enabled: setattr(u, "enabled", e))
        label = "Alerts resumed." if user.enabled else "Alerts paused. /on to resume."
        self.api.send_message(chat_id, label, reply_markup=REPLY_KEYBOARD)

    def _send_menu(self, chat_id, name: str = "", user: UserRule | None = None) -> None:
        user = user or self.rules.get_or_create(chat_id, name=name)
        self.api.send_message(
            chat_id,
            format_status(user),
            reply_markup=menu_keyboard(user),
        )


def _command_key(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("/"):
        t = t[1:]
        t = t.split("@", 1)[0]
        t = t.split(None, 1)[0]
    return t.lower()


def _is_command(text: str) -> bool:
    t = (text or "").strip()
    if t.startswith("/"):
        return True
    return t.lower() in (
        "⚙️ menu",
        "⚙ menu",
        "menu",
        "status",
        "pause",
        "resume",
        "help",
        "settings",
    )
