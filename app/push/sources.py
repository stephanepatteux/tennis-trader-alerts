"""Push sources that feed the :class:`PushHub`.

:class:`UltraPushSource` — the real feed. Connects to the Live Tennis API Ultra
WebSocket and publishes each score commit as it is written. Requires an ULTRA key.

Ported from live-tennis-scoreboard (``app/push/sources.py``).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

from ..config import ConfigError
from ..mapping import map_api_match
from .hub import PushHub


class PushSource:
    name = "base"

    def start(self, hub: PushHub) -> None:
        raise NotImplementedError


class UltraPushSource(PushSource):
    """Live Tennis API Ultra WebSocket push feed.

    Protocol (Centrifugo-style, per docs.livetennisapi.com):
      1. GET {base}/ws-token  (Authorization: Bearer <ULTRA key>)  -> token, ws_url, channels
      2. open ws_url
      3. send {"connect": {"token": token}, "id": 1}
      4. send {"subscribe": {"channel": "slate:all"}, "id": 2}
      5. receive {"push": {"channel": ..., "pub": {"data": <score frame>}}}
      6. reply to heartbeat {} with {}
    Tokens are short-lived: mint a fresh one on every reconnect and re-subscribe.
    """

    name = "livetennisapi-ultra"

    def __init__(self, api_key, base_url, model_fallback=True, timeout=10.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_fallback = model_fallback
        self.timeout = timeout
        self._thread = None
        self._stop = threading.Event()

    def start(self, hub: PushHub) -> None:
        self._thread = threading.Thread(
            target=self._run, args=(hub,), name="ultra-push", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # -- token minting ----------------------------------------------------
    def mint_ws_token(self) -> dict:
        req = urllib.request.Request(f"{self.base_url}/ws-token")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "tennis-trader-alerts/1.0")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- frame handling ---------------------------------------------------
    def handle_raw(self, raw, hub: PushHub, ws=None) -> None:
        """Parse one (possibly newline-batched) message and publish score frames.

        Returns nothing; sends a heartbeat reply through ``ws`` when the message is
        an empty object ``{}``.
        """
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg == {}:  # server heartbeat -> must reply promptly
                if ws is not None:
                    ws.send("{}")
                continue
            push = msg.get("push") if isinstance(msg, dict) else None
            if not push:
                continue  # connect/subscribe replies etc.
            data = (push.get("pub") or {}).get("data")
            if not isinstance(data, dict):
                continue
            match_id = data.get("id")
            if match_id is None:
                match_id = data.get("match_id")
            static = hub.static_for(match_id) if match_id is not None else {}
            hub.publish(map_api_match(data, self.model_fallback, static=static))

    def _run(self, hub: PushHub) -> None:
        # Imported lazily so unit tests need no websocket-client for handle_raw.
        # A missing library is a permanent, unrecoverable error, so let it end the
        # thread with a clear traceback rather than spinning in the reconnect loop.
        import websocket

        backoff = 1.0
        while not self._stop.is_set():
            ws = None
            try:
                info = self.mint_ws_token()
                ws_url = info["ws_url"]
                token = info["token"]
                channels = info.get("channels") or {}
                slate = channels.get("slate") or "slate:all"

                ws = websocket.create_connection(ws_url, timeout=self.timeout)
                ws.send(json.dumps({"connect": {"token": token}, "id": 1}))
                ws.send(json.dumps({"subscribe": {"channel": slate}, "id": 2}))
                backoff = 1.0  # connected cleanly

                while not self._stop.is_set():
                    raw = ws.recv()
                    if raw is None or raw == "":
                        continue
                    self.handle_raw(raw, hub, ws=ws)
            except Exception:
                # Connection dropped or token expired: reconnect with a fresh token.
                time.sleep(min(backoff, 30.0))
                backoff = min(backoff * 2, 30.0)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass


def get_push_source(model_fallback=None) -> UltraPushSource:
    """Build the Ultra source. An ULTRA key is required — there is no polling fallback."""
    api_key = os.environ.get("LIVE_TENNIS_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "LIVE_TENNIS_API_KEY is required. Real-time push is Ultra-only. "
            "Get a key at https://affiliates.livetennisapi.com/r/botblog (code botblog)."
        )
    if model_fallback is None:
        model_fallback = os.environ.get("MODEL_FALLBACK", "0") != "0"
    return UltraPushSource(
        api_key=api_key,
        base_url=os.environ.get(
            "LIVE_TENNIS_API_BASE", "https://api.livetennisapi.com/api/public/v1"
        ),
        model_fallback=model_fallback,
        timeout=float(os.environ.get("LIVE_TENNIS_API_TIMEOUT", "10")),
    )
