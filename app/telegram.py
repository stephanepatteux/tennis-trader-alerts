"""Telegram Bot API client.

The bot token is used only in the URL path and is never logged. HTTP errors are
re-raised without the request URL so a stack trace cannot leak the token.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.telegram.org"
USER_AGENT = "tennis-trader-alerts/1.0"


class TelegramApi:
    def __init__(self, token: str, api_base: str = DEFAULT_API_BASE, timeout: float = 10.0):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is empty")
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def call(self, method: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        url = f"{self.api_base}/bot{self.token}/{method}"
        body = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        wait = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            if "message is not modified" in detail.lower():
                return {"ok": True, "result": {}, "description": "message is not modified"}
            log.warning("Telegram %s failed http=%s body=%s", method, exc.code, detail[:300])
            raise RuntimeError(f"Telegram {method} HTTP {exc.code}") from None
        except urllib.error.URLError:
            raise RuntimeError(f"Telegram {method} network error") from None
        if not data.get("ok"):
            desc = data.get("description") or f"telegram {method} not ok"
            if "message is not modified" in str(desc).lower():
                return data
            log.warning("Telegram %s rejected desc=%s", method, desc)
            raise RuntimeError(desc)
        return data

    def send_message(
        self,
        chat_id,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self.call("sendMessage", payload)

    def edit_message_text(
        self,
        chat_id,
        message_id,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self.call("editMessageText", payload)

    def answer_callback_query(self, callback_query_id, text: str = "") -> dict:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return self.call("answerCallbackQuery", payload)

    def get_updates(self, offset: int = 0, timeout: int = 30) -> list:
        # Long-poll: HTTP timeout must exceed Telegram's timeout.
        data = self.call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=float(timeout) + 5.0,
        )
        return list(data.get("result") or [])

    def set_my_commands(self, commands: list[dict]) -> dict:
        return self.call("setMyCommands", {"commands": commands})
