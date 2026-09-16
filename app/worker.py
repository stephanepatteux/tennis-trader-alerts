"""Worker: consume the Ultra push feed and dispatch Telegram alerts."""

from __future__ import annotations

import logging
import os
import queue
import signal
import sys

from .bot import BotMenu
from .config import ConfigError, env_csv, load_dotenv, require_env
from .dispatch import Dispatcher, RateLimiter
from .notifier import LogNotifier, TelegramNotifier
from .push import PushHub, get_push_source
from .rules import RulesStore
from .telegram import TelegramApi

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_api(*, dry_run: bool) -> TelegramApi | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        if dry_run:
            return None
        require_env(
            "TELEGRAM_BOT_TOKEN",
            "Create a bot with @BotFather and put the token in .env — never commit it.",
        )
    return TelegramApi(
        token=token,
        api_base=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"),
        timeout=float(os.environ.get("TELEGRAM_TIMEOUT", "10")),
    )


def run(dry_run: bool = False) -> None:
    load_dotenv()
    _configure_logging()

    source = get_push_source()
    rules = RulesStore.load()
    api = build_api(dry_run=dry_run)
    notifier = LogNotifier() if dry_run else TelegramNotifier(api=api)
    dispatcher = Dispatcher(
        rules,
        notifier,
        rate_limiter=RateLimiter(
            max_events=int(os.environ.get("RATE_LIMIT_MAX", "20")),
            window_s=float(os.environ.get("RATE_LIMIT_WINDOW_S", "60")),
        ),
    )
    hub = PushHub(source_name=source.name)
    updates = hub.subscribe()
    source.start(hub)

    bot = None
    if api is not None:
        bot = BotMenu(api, rules, allowed_chats=env_csv("TELEGRAM_ALLOWED_CHATS"))
        bot.start()

    log.info(
        "Connected source=%s users=%d bot=%s",
        source.name,
        len(rules.users()),
        "on" if bot else "off",
    )

    stopping = False

    def _stop(*_args):
        nonlocal stopping
        stopping = True
        source.stop()
        if bot is not None:
            bot.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while not stopping:
            try:
                match = updates.get(timeout=1.0)
            except queue.Empty:
                rules.maybe_reload()
                continue
            dispatcher.handle(match)
    finally:
        source.stop()
        if bot is not None:
            bot.stop()
        hub.unsubscribe(updates)
        log.info("Worker stopped")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    try:
        run(dry_run=dry_run)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    return 0
